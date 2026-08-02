"""実PostgreSQLで認証とCSV取込を確認する任意実行の統合テスト。"""

import io
import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import delete, func, select

import database
from web.app import app


@unittest.skipUnless(
    os.environ.get("TEST_DATABASE_URL"),
    "TEST_DATABASE_URLが未設定のためPostgreSQL統合テストを省略",
)
class PostgreSQLIntegrationTest(unittest.TestCase):
    def test_register_login_and_sony_csv_import(self):
        username = f"postgres_test_{uuid.uuid4().hex}"
        postgres_url = os.environ["TEST_DATABASE_URL"]

        with patch.dict("os.environ", {"DATABASE_URL": postgres_url}):
            database.initialize_database()
            app.config.update(TESTING=True, SECRET_KEY="postgres-integration-test")
            client = app.test_client()
            try:
                registered = client.post(
                    "/register",
                    data={
                        "username": username,
                        "password": "password123",
                        "password_confirmation": "password123",
                    },
                    follow_redirects=True,
                )
                self.assertEqual(registered.status_code, 200)
                client.post("/logout")

                logged_in = client.post(
                    "/login",
                    data={"username": username, "password": "password123"},
                    follow_redirects=True,
                )
                self.assertEqual(logged_in.status_code, 200)

                csv_data = (Path(__file__).parent / "fixtures" / "FutsuRireki.csv").read_bytes()
                imported = client.post(
                    "/import-csv",
                    data={
                        "parser": "auto",
                        "csv_file": (io.BytesIO(csv_data), "FutsuRireki.csv"),
                    },
                    content_type="multipart/form-data",
                    follow_redirects=True,
                )
                self.assertEqual(imported.status_code, 200)
                self.assertIn("新規登録：4件", imported.get_data(as_text=True))
                user = database.get_user_by_username(username)
                with database.get_session() as session:
                    transaction_count = session.scalar(
                        select(func.count())
                        .select_from(database.TransactionModel)
                        .where(database.TransactionModel.user_id == user["id"])
                    )
                self.assertEqual(transaction_count, 4)
            finally:
                user = database.get_user_by_username(username)
                if user:
                    with database.get_session() as session:
                        session.execute(
                            delete(database.UserModel).where(database.UserModel.id == user["id"])
                        )
                        session.commit()
                database.clear_aggregate_cache()
