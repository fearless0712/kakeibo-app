"""Sony銀行CSV Parser。"""

import io

from .base import BaseParser


class SonyParser(BaseParser):
    source_key = "sony"
    display_name = "Sony銀行"
    import_name = "Sony銀行 明細CSV"
    detection_headers = (
        "預入額",
        "引出額",
        "差引残高",
        "お引出し金額",
        "支払額",
        "お預入れ金額",
        "摘要",
        "振込指定日",
        "受取人名",
        "振込金額",
    )

    DATE_COLUMNS = ("取引日", "日付", "年月日")
    DESCRIPTION_COLUMNS = ("摘要", "内容", "取引内容", "お取引内容")
    WITHDRAWAL_COLUMNS = (
        "引出額",
        "支払額",
        "お引出し金額",
        "出金額",
        "出金",
    )
    DEPOSIT_COLUMNS = ("預入額", "お預入れ金額", "入金額", "入金")
    AMOUNT_COLUMNS = ("金額", "取引金額")
    BALANCE_COLUMNS = ("差引残高", "残高", "取引後残高")
    TRANSFER_DATE_COLUMNS = ("振込指定日", "受付日", "取引日")
    TRANSFER_DESCRIPTION_COLUMNS = ("受取人名", "振込先", "振込先名", "受取人")
    TRANSFER_AMOUNT_COLUMNS = ("振込金額", "金額")
    TRANSFER_FEE_COLUMNS = ("振込手数料", "手数料")

    def parse(self, file):
        """Sony銀行CSVを銀行共通フォーマットへ変換します。"""
        data = self.read_bytes(file)
        normalized = self.normalize(self.decode_bytes(data))
        transfer_markers = ("振込指定日", "受取人名", "振込金額")
        if sum(marker in normalized for marker in transfer_markers) >= 2:
            self.import_name = "Sony銀行 振込CSV"
            return self.parse_transfer(io.BytesIO(data))

        self.import_name = "Sony銀行 普通預金CSV"
        aliases = (
            self.DATE_COLUMNS
            + self.DESCRIPTION_COLUMNS
            + self.WITHDRAWAL_COLUMNS
            + self.DEPOSIT_COLUMNS
            + self.AMOUNT_COLUMNS
            + self.BALANCE_COLUMNS
        )
        try:
            rows = self.extract_rows(io.BytesIO(data), aliases)
        except ValueError as error:
            self.add_error(0, error)
            return []

        transactions = []
        for row_number, row in enumerate(rows, start=2):
            try:
                date = self.parse_date(self.first_value(row, self.DATE_COLUMNS))
                description = self.first_value(row, self.DESCRIPTION_COLUMNS) or "取引"
                withdrawal = self.parse_amount(
                    self.first_value(row, self.WITHDRAWAL_COLUMNS), allow_empty=True
                )
                deposit = self.parse_amount(
                    self.first_value(row, self.DEPOSIT_COLUMNS), allow_empty=True
                )
                signed_amount = None
                if withdrawal in (None, 0) and deposit in (None, 0):
                    signed_amount = self.parse_amount(
                        self.first_value(row, self.AMOUNT_COLUMNS)
                    )
                amount, income_expense = self.classify_transaction(
                    description, withdrawal, deposit, signed_amount
                )
                balance = self.parse_amount(
                    self.first_value(row, self.BALANCE_COLUMNS), allow_empty=True
                )
                if amount <= 0:
                    raise ValueError("金額が0円です")
                transactions.append(
                    {
                        "date": date,
                        "description": description,
                        "amount": amount,
                        "type": income_expense,
                        "income_expense": income_expense,
                        "balance": balance,
                        "category": self.guess_category(description),
                    }
                )
            except (TypeError, ValueError) as error:
                self.add_error(row_number, error)
        return transactions

    def parse_transfer(self, file):
        """Sony銀行の振込CSVを支出取引へ変換します。"""
        aliases = (
            self.TRANSFER_DATE_COLUMNS
            + self.TRANSFER_DESCRIPTION_COLUMNS
            + self.TRANSFER_AMOUNT_COLUMNS
            + self.TRANSFER_FEE_COLUMNS
        )
        try:
            rows = self.extract_rows(file, aliases)
        except ValueError as error:
            self.add_error(0, error)
            return []

        transactions = []
        for row_number, row in enumerate(rows, start=2):
            try:
                date = self.parse_date(self.first_value(row, self.TRANSFER_DATE_COLUMNS))
                recipient = self.first_value(row, self.TRANSFER_DESCRIPTION_COLUMNS)
                amount = self.parse_amount(
                    self.first_value(row, self.TRANSFER_AMOUNT_COLUMNS)
                )
                fee = self.parse_amount(
                    self.first_value(row, self.TRANSFER_FEE_COLUMNS), allow_empty=True
                )
                total = abs(amount) + abs(fee or 0)
                if total <= 0:
                    raise ValueError("振込金額が0円です")
                description = f"振込 {recipient}".strip()
                transactions.append(
                    {
                        "date": date,
                        "description": description,
                        "amount": total,
                        "type": "expense",
                        "income_expense": "expense",
                        "balance": None,
                        "category": self.guess_category(description),
                    }
                )
            except (TypeError, ValueError) as error:
                self.add_error(row_number, error)
        return transactions

    @classmethod
    def classify_transaction(cls, description, withdrawal, deposit, signed_amount=None):
        """金額列を優先し、曖昧な場合は摘要から収入・支出を判定します。"""
        has_withdrawal = withdrawal not in (None, 0)
        has_deposit = deposit not in (None, 0)

        # Sony銀行の専用列に片方だけ金額がある場合は、列の意味を最優先します。
        if has_withdrawal and not has_deposit:
            return abs(withdrawal), "expense"
        if has_deposit and not has_withdrawal:
            return abs(deposit), "income"

        normalized = cls.normalize(description).upper().replace(" ", "")
        income_keywords = (
            "普通預金入金",
            "振込入金",
            "ATM入金",
            "給与",
            "利息",
            "入金",
        )
        expense_keywords = (
            "振込出金",
            "ATM出金",
            "デビット",
            "引落",
            "振替",
            "カード",
            "手数料",
            "VISA",
            "振込",
            "出金",
        )
        if any(keyword.upper() in normalized for keyword in income_keywords):
            kind = "income"
        elif any(keyword.upper() in normalized for keyword in expense_keywords):
            kind = "expense"
        elif signed_amount is not None:
            kind = "expense" if signed_amount < 0 else "income"
        elif has_withdrawal:
            kind = "expense"
        elif has_deposit:
            kind = "income"
        else:
            raise ValueError("預入額・引出額・金額のいずれも入力されていません")

        candidates = [value for value in (withdrawal, deposit, signed_amount) if value not in (None, 0)]
        if not candidates:
            raise ValueError("取引金額を判定できません")
        return abs(candidates[0]), kind

    @staticmethod
    def guess_category(description):
        """摘要のキーワードから既存カテゴリを推測します。"""
        normalized = SonyParser.normalize(description).upper().replace(" ", "")
        rules = (
            ("賞与", ("賞与", "ボーナス")),
            ("給与", ("給与",)),
            ("振込入金", ("振込入金", "普通預金入金")),
            ("利息", ("利息", "利子")),
            ("コンビニ", ("コンビニ", "セブン", "ローソン", "ファミリーマート")),
            ("スーパー", ("スーパー", "イオン", "イトーヨーカドー")),
            ("ドラッグストア", ("ドラッグ", "薬局", "マツモトキヨシ")),
            ("Amazon", ("AMAZON",)),
            ("楽天市場", ("楽天市場", "RAKUTEN")),
            ("公共料金", ("公共料金",)),
            ("光熱費", ("電気", "電力", "ガス", "水道")),
            ("通信費", ("携帯", "電話", "DOCOMO", "SOFTBANK", "KDDI", "AU")),
            ("サブスク", ("サブスク", "NETFLIX", "SPOTIFY", "YOUTUBE", "APPLE.COM/BILL")),
            ("現金・ATM", ("ATM",)),
            ("保険", ("保険",)),
            ("投資", ("投資", "証券", "NISA", "投資信託")),
            ("交通", ("鉄道", "電車", "JR", "SUICA", "PASMO", "バス", "タクシー", "交通", "ガソリン")),
            ("医療", ("病院", "クリニック", "医療", "歯科")),
            ("外食", ("レストラン", "カフェ", "食堂", "UBEREATS", "マクドナルド")),
            ("日用品", ("日用品", "ホームセンター", "ニトリ", "無印")),
            ("教育", ("学校", "学費", "授業料", "塾", "教育")),
            ("税金", ("税金", "住民税", "所得税", "国民年金")),
            ("手数料", ("手数料",)),
            ("カード", ("カード", "VISA", "MASTERCARD", "JCB", "デビット")),
            ("住居費", ("家賃", "賃料", "住宅ローン")),
            ("娯楽", ("映画", "ゲーム", "チケット", "GOOGLEPLAY")),
            ("食費", ("食品",)),
        )
        for category, keywords in rules:
            if any(keyword.upper() in normalized for keyword in keywords):
                return category
        return "その他"
