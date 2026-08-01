"""Web版の認証・データ分離・主要機能を確認するテスト。"""

import io
import importlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

import database
from web.parsers import detect_parser
from web.parsers.sony import SonyParser

web_app_module = importlib.import_module("web.app")
app = web_app_module.app


class WebAppTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        directory = Path(self.temporary_directory.name)
        database.DATABASE_FILE = directory / "test.db"
        database.LEGACY_CSV_FILE = directory / "missing.csv"
        database.LEGACY_BUDGET_FILE = directory / "missing.json"
        web_app_module.PENDING_IMPORT_DIR = directory / "pending_imports"
        database.initialize_database()
        app.config.update(TESTING=True, SECRET_KEY="test-secret-key")
        self.client = app.test_client()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def register(self, client, username):
        return client.post(
            "/register",
            data={
                "username": username,
                "password": "password123",
                "password_confirmation": "password123",
            },
            follow_redirects=True,
        )

    def test_login_is_required_and_pwa_files_are_public(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])
        response.close()

        expense_response = self.client.post("/expenses", data={})
        import_response = self.client.post("/import-csv", data={})
        self.assertIn("/login", expense_response.headers["Location"])
        self.assertIn("/login", import_response.headers["Location"])
        expense_response.close()
        import_response.close()

        login_page = self.client.get("/login")
        self.assertEqual(login_page.status_code, 200)
        self.assertIn("ログイン", login_page.get_data(as_text=True))
        login_page.close()

        manifest = self.client.get("/static/manifest.json")
        worker = self.client.get("/service-worker.js")
        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(worker.status_code, 200)
        manifest.close()
        worker.close()

    def test_register_password_hash_login_and_logout(self):
        response = self.register(self.client, "alice")
        self.assertIn("EQUA", response.get_data(as_text=True))
        response.close()

        user = database.get_user_by_username("alice")
        self.assertIsNotNone(user)
        self.assertNotEqual(user["password_hash"], "password123")
        self.assertTrue(user["password_hash"].startswith("$2"))

        self.client.post("/logout")
        bad_login = self.client.post(
            "/login", data={"username": "alice", "password": "wrong-password"}
        )
        self.assertIn("正しくありません", bad_login.get_data(as_text=True))
        bad_login.close()

        good_login = self.client.post(
            "/login",
            data={"username": "alice", "password": "password123"},
            follow_redirects=True,
        )
        self.assertEqual(good_login.status_code, 200)
        good_login.close()

    def test_expenses_and_budgets_are_isolated_by_user(self):
        self.register(self.client, "alice")
        self.client.post(
            "/expenses",
            data={
                "date": "2026-08-01",
                "category": "食費",
                "memo": "aliceの支出",
                "amount": "1200",
            },
        )
        self.client.post("/budget", data={"month": "2026-08", "budget": "50000"})
        alice = database.get_user_by_username("alice")
        alice_expense = database.get_expenses("2026-08", alice["id"])[0]

        second_client = app.test_client()
        self.register(second_client, "bob")
        bob_page = second_client.get("/?month=2026-08")
        self.assertNotIn("aliceの支出", bob_page.get_data(as_text=True))
        self.assertNotIn("50,000円", bob_page.get_data(as_text=True))
        bob_page.close()

        # 別ユーザーの支出IDを送っても削除できません。
        second_client.post(
            f"/expenses/{alice_expense['id']}/delete", data={"month": "2026-08"}
        )
        self.assertEqual(len(database.get_expenses("2026-08", alice["id"])), 1)

    def test_csv_import_belongs_to_logged_in_user(self):
        self.register(self.client, "alice")
        fixture = Path(__file__).parent / "fixtures" / "FutsuRireki.csv"
        csv_data = fixture.read_bytes()
        with self.assertLogs(app.logger, level="INFO") as logs:
            response = self.client.post(
                "/import-csv",
                data={
                    "parser": "auto",
                    "csv_file": (io.BytesIO(csv_data), "sony.csv"),
                },
                content_type="multipart/form-data",
                follow_redirects=True,
            )
        body = response.get_data(as_text=True)
        self.assertIn("Sony銀行 普通預金CSV", body)
        self.assertIn("新規登録：4件", body)
        self.assertIn("重複スキップ：0件", body)
        self.assertIn("使用Parser：SonyParser", body)
        self.assertIn("残高更新：998,750円", body)
        log_output = "\n".join(logs.output)
        self.assertIn("Import source: Sony銀行 普通預金CSV", log_output)
        self.assertIn("Imported: 4", log_output)
        self.assertIn("Skipped: 0", log_output)
        self.assertIn("Income: 2", log_output)
        self.assertIn("Expense: 2", log_output)
        response.close()

        alice = database.get_user_by_username("alice")
        # 全取引は4件、家計簿の支出一覧には出金2件だけが入ります。
        self.assertEqual(len(database.get_expenses("2026-08", alice["id"])), 2)
        with database.connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM transactions WHERE user_id = ?", (alice["id"],)
            ).fetchone()[0]
        self.assertEqual(count, 4)
        history = database.get_import_history(alice["id"])
        self.assertEqual(history[0]["csv_type"], "Sony銀行 普通預金CSV")
        self.assertEqual(history[0]["imported_count"], 4)

        # 同じCSVを再度取り込んでも重複登録されません。
        duplicate = self.client.post(
            "/import-csv",
            data={
                "parser": "auto",
                "csv_file": (io.BytesIO(csv_data), "sony.csv"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn("重複スキップ：4件", duplicate.get_data(as_text=True))
        self.assertEqual(len(database.get_expenses("2026-08", alice["id"])), 2)
        history = database.get_import_history(alice["id"])
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["skipped_count"], 4)
        duplicate.close()

        second_client = app.test_client()
        self.register(second_client, "bob")
        bob_id = database.get_user_by_username("bob")["id"]
        self.assertEqual(database.get_expenses("2026-08", bob_id), [])

    def test_sony_parser_cp932_and_auto_detection(self):
        # 金額にカンマがある実CSVでは通常引用符が付くため、有効な行でも確認します。
        valid_data = (
            '取引日,摘要,お引出し金額,お預入れ金額,残高\n'
            '2026/08/02,コンビニ,"1,200",,"98,800"\n'
        ).encode("cp932")
        self.assertIs(detect_parser(valid_data), SonyParser)
        parser = SonyParser()
        transactions = parser.parse(io.BytesIO(valid_data))
        self.assertEqual(transactions[0]["amount"], 1200)
        self.assertEqual(transactions[0]["income_expense"], "expense")
        self.assertEqual(transactions[0]["category"], "コンビニ")
        self.assertEqual(parser.errors, [])

    def test_sony_transfer_and_savings_csv_are_unified(self):
        self.register(self.client, "alice")
        fixture_directory = Path(__file__).parent / "fixtures"
        for filename in ("FutsuRireki.csv", "SonyTransfer.csv"):
            response = self.client.post(
                "/import-csv",
                data={
                    "parser": "auto",
                    "csv_file": (
                        io.BytesIO((fixture_directory / filename).read_bytes()),
                        filename,
                    ),
                },
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            response.close()

        alice = database.get_user_by_username("alice")
        with database.connect() as connection:
            sources = connection.execute(
                """
                SELECT source, COUNT(*) AS count FROM transactions
                WHERE user_id = ? GROUP BY source
                """,
                (alice["id"],),
            ).fetchall()
        self.assertEqual([(row["source"], row["count"]) for row in sources], [("sony", 6)])
        history = database.get_import_history(alice["id"])
        self.assertEqual(
            {item["csv_type"] for item in history},
            {"Sony銀行 普通預金CSV", "Sony銀行 振込CSV"},
        )
        self.assertTrue(all(item["bank"] == "Sony銀行" for item in history))
        self.assertEqual(sum(item["income_count"] for item in history), 2)
        self.assertEqual(sum(item["expense_count"] for item in history), 4)

        summary = database.get_financial_summary(alice["id"], "2026-08")
        self.assertEqual(summary["monthly_income"], 200100)
        self.assertEqual(summary["monthly_expense"], 53970)
        self.assertEqual(summary["monthly_net"], 146130)
        self.assertEqual(summary["current_balance"], 998750)
        self.assertEqual(summary["carried_balance"], 998750)

        # 別CSVを取り込んだ後も、同じCSVの再取込は新規追加せずスキップします。
        duplicate = self.client.post(
            "/import-csv",
            data={
                "parser": "auto",
                "csv_file": (
                    io.BytesIO((fixture_directory / "FutsuRireki.csv").read_bytes()),
                    "FutsuRireki.csv",
                ),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn("重複スキップ：4件", duplicate.get_data(as_text=True))
        duplicate.close()
        with database.connect() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM transactions WHERE user_id = ?",
                    (alice["id"],),
                ).fetchone()[0],
                6,
            )

    def test_admin_reset_keeps_users_and_other_user_data(self):
        self.register(self.client, "alice")
        alice = database.get_user_by_username("alice")
        database.add_expense("2026-08-01", "食費", "alice", 1000, alice["id"])
        database.set_month_budget("2026-08", 50000, alice["id"])
        database.import_bank_transactions(
            [
                {
                    "date": "2026-08-02",
                    "description": "ATM出金",
                    "amount": 500,
                    "income_expense": "expense",
                    "balance": 99500,
                    "category": "その他",
                }
            ],
            alice["id"],
            "sony",
            "Sony銀行 普通預金CSV",
        )

        second_client = app.test_client()
        self.register(second_client, "bob")
        bob = database.get_user_by_username("bob")
        database.add_expense("2026-08-01", "食費", "bob", 2000, bob["id"])

        response = self.client.post(
            "/admin/reset", data={"confirmation": "RESET"}, follow_redirects=True
        )
        self.assertIn("全データをリセットしました", response.get_data(as_text=True))
        response.close()
        self.assertIsNotNone(database.get_user_by_username("alice"))
        self.assertEqual(database.get_expenses(user_id=alice["id"]), [])
        self.assertEqual(database.get_import_history(alice["id"]), [])
        self.assertEqual(database.get_budgets(alice["id"])["2026-08"], 50000)
        self.assertEqual(len(database.get_expenses(user_id=bob["id"])), 1)

    def test_futsu_rireki_csv_format(self):
        fixture = Path(__file__).parent / "fixtures" / "FutsuRireki.csv"
        data = fixture.read_bytes()
        self.assertIs(detect_parser(data), SonyParser)

        parser = SonyParser()
        transactions = parser.parse(io.BytesIO(data))
        self.assertEqual(len(transactions), 4)
        self.assertEqual(parser.errors, [])

        income = transactions[0]
        self.assertEqual(income["date"], "2026-08-01")
        self.assertEqual(income["description"], "給与振込")
        self.assertEqual(income["amount"], 200000)
        self.assertEqual(income["income_expense"], "income")
        self.assertEqual(income["type"], "income")
        self.assertEqual(income["balance"], 1000000)

        expense = transactions[1]
        self.assertEqual(expense["amount"], 1250)
        self.assertEqual(expense["income_expense"], "expense")
        self.assertEqual(expense["type"], "expense")
        self.assertEqual(expense["balance"], 998750)

        # 空欄とNaNの残高は、文字列ではなくNoneとして扱います。
        self.assertIsNone(transactions[2]["balance"])
        self.assertIsNone(transactions[3]["balance"])

    def test_sony_income_expense_keyword_rules(self):
        income_descriptions = ("給与", "振込入金", "ATM入金", "普通預金利息", "入金")
        expense_descriptions = (
            "振込",
            "振込出金",
            "デビット利用",
            "口座振替引落",
            "ATM出金",
            "振込手数料",
            "Visaデビット",
        )
        # 両方の金額列がある曖昧なケースでは、摘要の具体的な語句で判定します。
        for description in income_descriptions:
            amount, kind = SonyParser.classify_transaction(
                description, withdrawal=1000, deposit=1000
            )
            self.assertEqual((amount, kind), (1000, "income"), description)
        for description in expense_descriptions:
            amount, kind = SonyParser.classify_transaction(
                description, withdrawal=1000, deposit=1000
            )
            self.assertEqual((amount, kind), (1000, "expense"), description)

        # 専用金額列が片方だけの場合は、摘要より金額列を優先します。
        self.assertEqual(
            SonyParser.classify_transaction("給与", withdrawal=500, deposit=None),
            (500, "expense"),
        )
        self.assertEqual(
            SonyParser.classify_transaction("Visa", withdrawal=None, deposit=500),
            (500, "income"),
        )

    def test_sony_payment_column_and_saved_type_history_counts(self):
        self.register(self.client, "alice")
        csv_data = (
            "取引日,摘要,預入額,支払額,差引残高\n"
            "2026/08/10,普通預金入金,50000,,150000\n"
            "2026/08/11,カード引落,,12000,138000\n"
        ).encode("utf-8")
        response = self.client.post(
            "/import-csv",
            data={
                "parser": "auto",
                "csv_file": (io.BytesIO(csv_data), "sony-current.csv"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        response.close()

        user_id = database.get_user_by_username("alice")["id"]
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT amount, date, description, category, balance, type
                FROM transactions WHERE user_id = ? ORDER BY date
                """,
                (user_id,),
            ).fetchall()
        self.assertEqual([row["type"] for row in rows], ["income", "expense"])
        self.assertEqual(rows[0]["amount"], 50000)
        self.assertEqual(rows[1]["balance"], 138000)
        self.assertTrue(all(row["category"] for row in rows))

        history = database.get_import_history(user_id)[0]
        self.assertEqual(history["income_count"], 1)
        self.assertEqual(history["expense_count"], 1)
        summary = database.get_financial_summary(user_id, "2026-08")
        self.assertEqual(summary["monthly_income"], 50000)
        self.assertEqual(summary["monthly_expense"], 12000)

    def test_sony_category_guessing(self):
        cases = {
            "8月分給与": "給与",
            "セブンイレブン デビット": "コンビニ",
            "JR東日本 SUICA": "交通",
            "東京電力 引落": "光熱費",
            "ドラッグストア": "ドラッグストア",
            "NETFLIX.COM Visa": "サブスク",
            "振込手数料": "手数料",
            "Amazon.co.jp": "Amazon",
            "大学 授業料": "教育",
            "NISA 投資信託": "投資",
        }
        for description, expected in cases.items():
            self.assertEqual(SonyParser.guess_category(description), expected)

    def test_unknown_csv_requests_bank_selection(self):
        self.register(self.client, "alice")
        response = self.client.post(
            "/import-csv",
            data={
                "parser": "auto",
                "csv_file": (io.BytesIO(b"unknown,columns\n1,2\n"), "unknown.csv"),
            },
            content_type="multipart/form-data",
        )
        body = response.get_data(as_text=True)
        self.assertIn("自動判定できませんでした", body)
        self.assertIn("金融機関を選択", body)
        response.close()

    def test_asset_dashboard_drag_drop_and_import_history_actions(self):
        self.register(self.client, "alice")
        fixture = Path(__file__).parent / "fixtures" / "FutsuRireki.csv"
        response = self.client.post(
            "/import-csv",
            data={
                "parser": "auto",
                "csv_file": (io.BytesIO(fixture.read_bytes()), "FutsuRireki.csv"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        body = response.get_data(as_text=True)
        self.assertIn("資産一覧", body)
        self.assertIn("合計資産", body)
        self.assertIn("月別資産推移", body)
        self.assertIn("998,750円", body)
        response.close()

        import_page = self.client.get("/import-csv")
        self.assertIn("ドラッグ＆ドロップ", import_page.get_data(as_text=True))
        import_page.close()

        user_id = database.get_user_by_username("alice")["id"]
        history = database.get_import_history(user_id)
        self.assertTrue(history[0]["can_reimport"])
        history_id = history[0]["id"]
        admin_page = self.client.get("/admin")
        admin_body = admin_page.get_data(as_text=True)
        for label in ("銀行", "CSV種類", "取込件数", "収入件数", "支出件数", "重複件数", "再インポート", "取込削除"):
            self.assertIn(label, admin_body)
        admin_page.close()

        reimported = self.client.post(
            f"/admin/import-history/{history_id}/reimport", follow_redirects=True
        )
        self.assertIn("追加 0件 / 重複 4件", reimported.get_data(as_text=True))
        reimported.close()
        newest_history_id = database.get_import_history(user_id)[0]["id"]
        deleted = self.client.post(
            f"/admin/import-history/{newest_history_id}/delete", follow_redirects=True
        )
        self.assertIn("インポートを取り消しました", deleted.get_data(as_text=True))
        deleted.close()
        # 重複だけの再取込履歴には取引が紐付かないため、元の取込を取り消します。
        deleted = self.client.post(
            f"/admin/import-history/{history_id}/delete", follow_redirects=True
        )
        self.assertIn("削除取引：4件", deleted.get_data(as_text=True))
        deleted.close()
        with database.connect() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM transactions WHERE user_id = ?", (user_id,)
                ).fetchone()[0],
                0,
            )
        self.assertEqual(database.get_expenses(user_id=user_id), [])
        self.assertEqual(database.get_lifetime_statistics(user_id)["lifetime_stats"]["transaction_count"], 0)
        self.assertEqual(database.get_lifetime_statistics(user_id)["lifetime_stats"]["current_assets"], 0)
        self.assertEqual(database.get_category_ranking(user_id), [])

    def test_multiple_accounts_are_kept_separate(self):
        self.register(self.client, "alice")
        user_id = database.get_user_by_username("alice")["id"]
        for account_key, account_name, balance in (
            ("sony:savings", "普通預金", 120000),
            ("sony:sub", "貯蓄預金", 80000),
        ):
            database.import_bank_transactions(
                [{
                    "date": "2026-08-01",
                    "description": account_name,
                    "amount": balance,
                    "type": "income",
                    "balance": balance,
                    "category": "その他",
                }],
                user_id=user_id,
                source=account_key,
                bank="Sony銀行",
                account_key=account_key,
                account_name=account_name,
                csv_type=account_name,
            )
        assets = database.get_asset_dashboard(user_id, "2026-08")
        self.assertEqual(len(assets["bank_assets"]), 2)
        self.assertEqual({item["name"] for item in assets["bank_assets"]}, {"普通預金", "貯蓄預金"})
        self.assertEqual(assets["total_assets"], 200000)

    def test_lifetime_statistics_and_monthly_charts(self):
        self.register(self.client, "alice")
        user_id = database.get_user_by_username("alice")["id"]
        database.import_bank_transactions(
            [
                {
                    "date": "2026-01-15",
                    "description": "給与",
                    "amount": 100000,
                    "type": "income",
                    "balance": 100000,
                    "category": "給与",
                },
                {
                    "date": "2026-03-10",
                    "description": "家賃",
                    "amount": 40000,
                    "type": "expense",
                    "balance": 60000,
                    "category": "住居費",
                },
            ],
            user_id=user_id,
            source="sony",
            csv_type="統計テスト",
            bank="Sony銀行",
        )
        statistics = database.get_lifetime_statistics(user_id)
        stats = statistics["lifetime_stats"]
        self.assertEqual(stats["total_income"], 100000)
        self.assertEqual(stats["total_expense"], 40000)
        self.assertEqual(stats["lifetime_net"], 60000)
        self.assertEqual(stats["current_assets"], 60000)
        self.assertEqual(stats["transaction_count"], 2)
        # 1月から3月までの3か月（取引のない2月も含む）で平均します。
        self.assertEqual(stats["average_monthly_income"], 33333)
        self.assertEqual(stats["average_monthly_expense"], 13333)
        self.assertEqual(stats["highest_balance"], 100000)
        self.assertEqual(stats["lowest_balance"], 60000)
        self.assertEqual(statistics["cashflow_chart"]["labels"], ["2026-01", "2026-02", "2026-03"])
        self.assertEqual(statistics["cashflow_chart"]["net"], [100000, 0, -40000])
        self.assertEqual(statistics["lifetime_asset_chart"]["values"], [100000, 100000, 60000])
        self.assertEqual(statistics["lifetime_asset_chart"]["previous"], [0, 100000, 100000])
        self.assertEqual(statistics["lifetime_asset_chart"]["carryover"], [100000, 100000, 60000])
        ranking = database.get_category_ranking(user_id)
        self.assertEqual(ranking[0]["category"], "住居費")
        reports = database.get_annual_reports(user_id)
        self.assertEqual(reports[0]["income"], 100000)
        self.assertEqual(reports[0]["expense"], 40000)
        self.assertEqual(reports[0]["savings"], 60000)
        self.assertEqual(reports[0]["savings_rate"], 60.0)

        searched = database.search_transactions(user_id, query="家賃")
        self.assertEqual(len(searched), 1)
        self.assertEqual(searched[0]["type"], "expense")
        income_only = database.search_transactions(user_id, filter_kind="income")
        self.assertEqual([item["description"] for item in income_only], ["給与"])
        bank_only = database.search_transactions(user_id, bank="Sony銀行")
        self.assertEqual(len(bank_only), 2)

        page = self.client.get("/?month=2026-03").get_data(as_text=True)
        for label in (
            "総収入",
            "総支出",
            "累計収支",
            "現在資産",
            "総取引件数",
            "平均月収",
            "平均月支出",
            "過去最高残高",
            "過去最低残高",
            "月別収支推移",
            "月別資産推移",
            "支出カテゴリーランキング",
            "年間レポート",
            "取引検索",
            "Version 2.0.0",
        ):
            self.assertIn(label, page)
        self.assertIn("chart.js", page)

        filtered_page = self.client.get("/?month=2026-03&q=家賃").get_data(as_text=True)
        self.assertIn("家賃", filtered_page)
        self.assertNotIn(">給与</td>", filtered_page)

    def test_parser_failure_is_flashed_on_dashboard(self):
        self.register(self.client, "alice")
        response = self.client.post(
            "/import-csv",
            data={
                "parser": "sony",
                "csv_file": (io.BytesIO(b"wrong,headers\n1,2\n"), "invalid.csv"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        body = response.get_data(as_text=True)
        self.assertIn("必要な列が見つかりません", body)
        self.assertIn("使用Parser：SonyParser", body)
        response.close()

    def test_existing_database_schema_is_migrated(self):
        database.DATABASE_FILE.unlink()
        with sqlite3.connect(database.DATABASE_FILE) as connection:
            connection.executescript(
                """
                CREATE TABLE expenses (
                    id INTEGER PRIMARY KEY, date TEXT, category TEXT,
                    memo TEXT, amount INTEGER
                );
                INSERT INTO expenses VALUES (1, '2026-08-01', '食費', '旧データ', 900);
                CREATE TABLE budgets (month TEXT PRIMARY KEY, amount INTEGER);
                INSERT INTO budgets VALUES ('2026-08', 30000);
                """
            )
        database.initialize_database()
        with database.connect() as connection:
            self.assertIn("user_id", database.table_columns(connection, "expenses"))
            self.assertIn("user_id", database.table_columns(connection, "budgets"))
            self.assertTrue(database.table_columns(connection, "transactions"))
            self.assertIn(
                "import_history_id", database.table_columns(connection, "transactions")
            )
            self.assertTrue(database.table_columns(connection, "accounts"))
            self.assertTrue(database.table_columns(connection, "import_history"))
            self.assertIsNotNone(
                connection.execute("SELECT 1 FROM users LIMIT 1").description
            )


if __name__ == "__main__":
    unittest.main()
