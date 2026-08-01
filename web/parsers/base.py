"""銀行・カード会社CSV Parserの共通機能。"""

import csv
import io
import unicodedata
from abc import ABC, abstractmethod
from datetime import datetime


class BaseParser(ABC):
    """全Parserが継承する基底クラス。"""

    source_key = "base"
    display_name = "未設定"
    import_name = "未設定CSV"
    detection_headers = ()

    def __init__(self):
        self.errors = []

    @abstractmethod
    def parse(self, file):
        """CSVを共通フォーマットの辞書リストへ変換します。"""

    @classmethod
    def detection_score(cls, data):
        """ヘッダー候補の一致数から自動判定スコアを返します。"""
        text = cls.decode_bytes(data)
        normalized = cls.normalize(text)
        return sum(1 for header in cls.detection_headers if cls.normalize(header) in normalized)

    @staticmethod
    def read_bytes(file):
        """FileStorage、BytesIO、bytesのいずれからもバイト列を取得します。"""
        if isinstance(file, bytes):
            return file
        if isinstance(file, str):
            return file.encode("utf-8")
        position = file.tell() if hasattr(file, "tell") else None
        data = file.read()
        if position is not None and hasattr(file, "seek"):
            file.seek(position)
        return data.encode("utf-8") if isinstance(data, str) else data

    @staticmethod
    def decode_bytes(data):
        """日本の金融機関で多いUTF-8とCP932を処理します。"""
        for encoding in ("utf-8-sig", "cp932"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("文字コードを判定できません（UTF-8またはShift_JISを使用してください）")

    @staticmethod
    def normalize(value):
        """全角・半角と余分な空白を揃えます。"""
        return unicodedata.normalize("NFKC", str(value or "")).strip()

    def extract_rows(self, file, header_aliases):
        """CSV内のヘッダー行を探し、正規化済みの辞書を返します。"""
        data = self.read_bytes(file)
        text = self.decode_bytes(data)
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(io.StringIO(text), dialect))
        expected = {self.normalize(header) for header in header_aliases}
        header_index = None
        for index, row in enumerate(rows[:20]):
            matches = sum(1 for value in row if self.normalize(value) in expected)
            if matches >= 2:
                header_index = index
                break
        if header_index is None:
            raise ValueError("対応するヘッダー行が見つかりません")

        headers = [self.normalize(value) for value in rows[header_index]]
        records = []
        for row in rows[header_index + 1 :]:
            if not any(self.normalize(value) for value in row):
                continue
            padded = row + [""] * (len(headers) - len(row))
            records.append(
                {header: self.normalize(padded[i]) for i, header in enumerate(headers)}
            )
        return records

    @classmethod
    def first_value(cls, row, aliases):
        """候補列のうち最初に値が入っているものを返します。"""
        for alias in aliases:
            value = row.get(cls.normalize(alias), "")
            if value and cls.normalize(value).lower() not in {
                "nan",
                "null",
                "none",
                "-",
                "--",
            }:
                return value
        return ""

    @classmethod
    def parse_amount(cls, value, allow_empty=False):
        """カンマ、円記号、△、括弧付きの金額を整数へ変換します。"""
        text = cls.normalize(value).replace(",", "").replace("円", "").replace("¥", "")
        if text.lower() in {"nan", "null", "none", "-", "--"}:
            text = ""
        if not text and allow_empty:
            return None
        negative = text.startswith(("-", "△")) or (text.startswith("(") and text.endswith(")"))
        text = text.lstrip("-△").strip("() ")
        if not text:
            if allow_empty:
                return None
            raise ValueError("金額が空です")
        number = int(float(text))
        return -number if negative else number

    @classmethod
    def parse_date(cls, value):
        """一般的な日本向け日付をYYYY-MM-DDへ揃えます。"""
        text = cls.normalize(value)
        for format_string in ("%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d", "%Y年%m月%d日"):
            try:
                return datetime.strptime(text, format_string).strftime("%Y-%m-%d")
            except ValueError:
                continue
        raise ValueError(f"日付形式を読み取れません: {text}")

    def add_error(self, row_number, message):
        self.errors.append({"row": row_number, "message": str(message)})


class UnsupportedParser(BaseParser):
    """今後実装する金融機関Parserの雛形。"""

    def parse(self, file):
        self.read_bytes(file)
        self.add_error(0, f"{self.display_name} Parserは現在準備中です")
        return []
