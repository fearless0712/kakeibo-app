"""Web版の主要機能を確認するテスト。"""

import tempfile
import unittest
from pathlib import Path

import database
from web.app import app


class WebAppTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        directory = Path(self.temporary_directory.name)
        database.DATABASE_FILE = directory / "test.db"
        database.LEGACY_CSV_FILE = directory / "missing.csv"
        database.LEGACY_BUDGET_FILE = directory / "missing.json"
        database.initialize_database()
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_home_and_pwa_files(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("かんたん家計簿", response.get_data(as_text=True))
        response.close()
        manifest = self.client.get("/static/manifest.json")
        worker = self.client.get("/service-worker.js")
        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(worker.status_code, 200)
        manifest.close()
        worker.close()

    def test_add_budget_and_delete_expense(self):
        response = self.client.post(
            "/expenses",
            data={
                "date": "2026-08-01",
                "category": "食費",
                "memo": "テスト",
                "amount": "1200",
            },
            follow_redirects=True,
        )
        self.assertIn("1,200円", response.get_data(as_text=True))
        expense_id = database.get_expenses("2026-08")[0]["id"]

        self.client.post("/budget", data={"month": "2026-08", "budget": "50000"})
        self.assertEqual(database.get_budgets()["2026-08"], 50000)

        self.client.post(
            f"/expenses/{expense_id}/delete", data={"month": "2026-08"}
        )
        self.assertEqual(database.get_expenses("2026-08"), [])


if __name__ == "__main__":
    unittest.main()
