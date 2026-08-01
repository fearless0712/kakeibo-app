"""デスクトップ版とWeb版で共有するSQLiteデータ層。"""

import csv
import json
import sqlite3
import sys
from pathlib import Path


def get_data_directory():
    """実行方法に合わせてユーザーデータの保存先を返します。"""
    if getattr(sys, "frozen", False):
        directory = Path.home() / "Library" / "Application Support" / "Kakeibo"
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    return Path(__file__).parent


DATABASE_FILE = get_data_directory() / "kakeibo.db"
LEGACY_CSV_FILE = get_data_directory() / "kakeibo.csv"
LEGACY_BUDGET_FILE = get_data_directory() / "budgets.json"


def connect():
    """列名で値を取得できるSQLite接続を作ります。"""
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    """テーブルを作り、必要なら旧CSV/JSONデータを移行します。"""
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                category TEXT NOT NULL,
                memo TEXT NOT NULL DEFAULT '',
                amount INTEGER NOT NULL CHECK (amount > 0)
            );

            CREATE TABLE IF NOT EXISTS budgets (
                month TEXT PRIMARY KEY,
                amount INTEGER NOT NULL CHECK (amount >= 0)
            );

            CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
            CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);
            """
        )
        expense_count = connection.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        budget_count = connection.execute("SELECT COUNT(*) FROM budgets").fetchone()[0]
        if expense_count == 0:
            migrate_legacy_expenses(connection)
        if budget_count == 0:
            migrate_legacy_budgets(connection)


def migrate_legacy_expenses(connection):
    """既存のCSV支出データをSQLiteへ一度だけ取り込みます。"""
    if not LEGACY_CSV_FILE.exists():
        return
    with LEGACY_CSV_FILE.open("r", newline="", encoding="utf-8-sig") as file:
        for record in csv.DictReader(file):
            try:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO expenses (id, date, category, memo, amount)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        int(record["id"]),
                        record["date"],
                        record["category"],
                        record.get("memo", ""),
                        int(record["amount"]),
                    ),
                )
            except (KeyError, TypeError, ValueError):
                continue


def migrate_legacy_budgets(connection):
    """既存のJSON予算データをSQLiteへ一度だけ取り込みます。"""
    if not LEGACY_BUDGET_FILE.exists():
        return
    try:
        with LEGACY_BUDGET_FILE.open("r", encoding="utf-8") as file:
            budgets = json.load(file)
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(budgets, dict):
        return
    for month, amount in budgets.items():
        try:
            connection.execute(
                "INSERT OR REPLACE INTO budgets (month, amount) VALUES (?, ?)",
                (month, int(amount)),
            )
        except (TypeError, ValueError, sqlite3.IntegrityError):
            continue


def get_expenses(month=None):
    """支出を新しい順に取得します。monthを指定すると月別になります。"""
    initialize_database()
    query = "SELECT id, date, category, memo, amount FROM expenses"
    parameters = ()
    if month:
        query += " WHERE date LIKE ?"
        parameters = (f"{month}-%",)
    query += " ORDER BY date DESC, id DESC"
    with connect() as connection:
        return [dict(row) for row in connection.execute(query, parameters).fetchall()]


def add_expense(date, category, memo, amount):
    """支出を1件追加してIDを返します。"""
    initialize_database()
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO expenses (date, category, memo, amount) VALUES (?, ?, ?, ?)",
            (date, category, memo, amount),
        )
        return cursor.lastrowid


def delete_expense(expense_id):
    """IDで支出を削除します。"""
    initialize_database()
    with connect() as connection:
        cursor = connection.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        return cursor.rowcount > 0


def replace_expenses(records):
    """互換性のため支出データ全体を置き換えます。"""
    initialize_database()
    with connect() as connection:
        connection.execute("DELETE FROM expenses")
        connection.executemany(
            """
            INSERT INTO expenses (id, date, category, memo, amount)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    int(record["id"]),
                    record["date"],
                    record["category"],
                    record.get("memo", ""),
                    int(record["amount"]),
                )
                for record in records
            ],
        )


def get_budgets():
    """全ての月別予算を辞書で返します。"""
    initialize_database()
    with connect() as connection:
        rows = connection.execute("SELECT month, amount FROM budgets").fetchall()
        return {row["month"]: row["amount"] for row in rows}


def set_month_budget(month, amount):
    """指定月の予算を追加または更新します。"""
    initialize_database()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO budgets (month, amount) VALUES (?, ?)
            ON CONFLICT(month) DO UPDATE SET amount = excluded.amount
            """,
            (month, amount),
        )
