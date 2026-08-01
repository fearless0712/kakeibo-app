"""デスクトップ版とWeb版で共有するSQLiteデータ層。"""

import csv
import hashlib
import json
import os
import sqlite3
import sys
from functools import lru_cache
from pathlib import Path


def get_data_directory():
    """実行方法に合わせてユーザーデータの保存先を返します。"""
    configured = os.environ.get("EQUA_DATA_DIR")
    if configured:
        directory = Path(configured).expanduser()
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    if getattr(sys, "frozen", False):
        directory = Path.home() / "Library" / "Application Support" / "Kakeibo"
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    return Path(__file__).parent


DATABASE_FILE = get_data_directory() / "kakeibo.db"
LEGACY_CSV_FILE = get_data_directory() / "kakeibo.csv"
LEGACY_BUDGET_FILE = get_data_directory() / "budgets.json"
_CACHE_DATABASE_FILE = None


def connect():
    """列名で値を取得できるSQLite接続を作ります。"""
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def table_columns(connection, table_name):
    """テーブルに存在する列名を集合で返します。"""
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def initialize_database():
    """テーブルを作り、既存DBとCSV/JSONを安全にマイグレーションします。"""
    global _CACHE_DATABASE_FILE
    database_key = str(DATABASE_FILE.resolve())
    if _CACHE_DATABASE_FILE != database_key:
        clear_aggregate_cache()
        _CACHE_DATABASE_FILE = database_key
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                institution TEXT NOT NULL,
                account_key TEXT NOT NULL,
                name TEXT NOT NULL,
                current_balance INTEGER,
                UNIQUE(user_id, account_key),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                account_id INTEGER,
                source TEXT NOT NULL,
                date TEXT NOT NULL,
                description TEXT NOT NULL,
                amount INTEGER NOT NULL CHECK (amount >= 0),
                type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                balance INTEGER,
                category TEXT NOT NULL DEFAULT 'その他',
                fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, fingerprint),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS import_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                csv_type TEXT NOT NULL,
                imported_count INTEGER NOT NULL DEFAULT 0,
                skipped_count INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT NOT NULL,
                category TEXT NOT NULL,
                memo TEXT NOT NULL DEFAULT '',
                amount INTEGER NOT NULL CHECK (amount > 0),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        # 認証追加前のexpensesテーブルにはuser_idがないため列を追加します。
        if "user_id" not in table_columns(connection, "expenses"):
            connection.execute("ALTER TABLE expenses ADD COLUMN user_id INTEGER")
        if "transaction_id" not in table_columns(connection, "expenses"):
            connection.execute("ALTER TABLE expenses ADD COLUMN transaction_id INTEGER")

        migrate_budgets_schema(connection)
        migrate_import_history_schema(connection)
        migrate_transactions_schema(connection)
        migrate_bank_transactions_schema(connection)
        connection.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_expenses_user_date
                ON expenses(user_id, date);
            CREATE INDEX IF NOT EXISTS idx_expenses_category
                ON expenses(category);
            CREATE INDEX IF NOT EXISTS idx_transactions_user_date
                ON transactions(user_id, date);
            CREATE INDEX IF NOT EXISTS idx_transactions_account_date
                ON transactions(account_id, date);
            CREATE INDEX IF NOT EXISTS idx_transactions_import_history
                ON transactions(import_history_id);
            CREATE INDEX IF NOT EXISTS idx_import_history_user_date
                ON import_history(user_id, imported_at);
            """
        )

        expense_count = connection.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        budget_count = connection.execute("SELECT COUNT(*) FROM budgets").fetchone()[0]
        if expense_count == 0:
            migrate_legacy_expenses(connection)
        if budget_count == 0:
            migrate_legacy_budgets(connection)
        sync_unlinked_expenses(connection)


def migrate_import_history_schema(connection):
    """v2.1以前のインポート履歴へ資産管理用の列を追加します。"""
    columns = table_columns(connection, "import_history")
    additions = {
        "bank": "TEXT NOT NULL DEFAULT '不明'",
        "income_count": "INTEGER NOT NULL DEFAULT 0",
        "expense_count": "INTEGER NOT NULL DEFAULT 0",
        "filename": "TEXT",
        "parser_key": "TEXT",
        "raw_csv": "BLOB",
    }
    for column, definition in additions.items():
        if column not in columns:
            connection.execute(
                f"ALTER TABLE import_history ADD COLUMN {column} {definition}"
            )


def migrate_transactions_schema(connection):
    """Version 2のCSV単位取消用リンクを既存台帳へ追加します。"""
    if "import_history_id" not in table_columns(connection, "transactions"):
        connection.execute("ALTER TABLE transactions ADD COLUMN import_history_id INTEGER")


def clear_aggregate_cache():
    """取引更新後にダッシュボード集計キャッシュを破棄します。"""
    for function_name in (
        "get_asset_dashboard",
        "get_lifetime_statistics",
        "get_annual_reports",
        "get_category_ranking",
    ):
        function = globals().get(function_name)
        if function and hasattr(function, "cache_clear"):
            function.cache_clear()


def get_or_create_account(connection, user_id, institution, account_key, name):
    """金融機関の口座を取得し、なければ作成します。"""
    connection.execute(
        """
        INSERT OR IGNORE INTO accounts (user_id, institution, account_key, name)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, institution, account_key, name),
    )
    return connection.execute(
        "SELECT id FROM accounts WHERE user_id = ? AND account_key = ?",
        (user_id, account_key),
    ).fetchone()["id"]


def refresh_account_balance(connection, account_id):
    """口座の最新残高を台帳の最終残高から更新します。"""
    row = connection.execute(
        """
        SELECT balance FROM transactions
        WHERE account_id = ? AND balance IS NOT NULL
        ORDER BY date DESC, id DESC LIMIT 1
        """,
        (account_id,),
    ).fetchone()
    connection.execute(
        "UPDATE accounts SET current_balance = ? WHERE id = ?",
        (row["balance"] if row else None, account_id),
    )


def migrate_bank_transactions_schema(connection):
    """旧bank_transactionsを共通の資産台帳transactionsへ移行します。"""
    old_table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'bank_transactions'"
    ).fetchone()
    if not old_table:
        return
    rows = connection.execute(
        """
        SELECT user_id, source, date, description, amount, income_expense,
               balance, category, fingerprint, created_at
        FROM bank_transactions ORDER BY id
        """
    ).fetchall()
    account_ids = {}
    for row in rows:
        account_key = f"{row['source']}:default"
        key = (row["user_id"], account_key)
        if key not in account_ids:
            account_ids[key] = get_or_create_account(
                connection,
                row["user_id"],
                row["source"],
                account_key,
                f"{row['source']} 口座",
            )
        connection.execute(
            """
            INSERT OR IGNORE INTO transactions
                (user_id, account_id, source, date, description, amount,
                 type, balance, category, fingerprint, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["user_id"],
                account_ids[key],
                row["source"],
                row["date"],
                row["description"],
                row["amount"],
                row["income_expense"],
                row["balance"],
                row["category"],
                row["fingerprint"],
                row["created_at"],
            ),
        )
    for account_id in set(account_ids.values()):
        refresh_account_balance(connection, account_id)
    connection.execute("DROP TABLE bank_transactions")


def sync_unlinked_expenses(connection, user_id=None):
    """旧データの手入力支出を共通資産台帳へ安全に反映します。"""
    query = "SELECT * FROM expenses WHERE transaction_id IS NULL AND user_id IS NOT NULL"
    parameters = []
    if user_id is not None:
        query += " AND user_id = ?"
        parameters.append(user_id)
    for expense in connection.execute(query, parameters).fetchall():
        # 旧銀行取込の支出は、先に移行した台帳取引に紐付けます。
        match = connection.execute(
            """
            SELECT id FROM transactions
            WHERE user_id = ? AND type = 'expense' AND date = ? AND amount = ?
              AND description = ?
            ORDER BY id LIMIT 1
            """,
            (expense["user_id"], expense["date"], expense["amount"], expense["memo"]),
        ).fetchone()
        if match:
            transaction_id = match["id"]
        else:
            account_id = get_or_create_account(
                connection,
                expense["user_id"],
                "manual",
                "manual:default",
                "手入力",
            )
            cursor = connection.execute(
                """
                INSERT INTO transactions
                    (user_id, account_id, source, date, description, amount,
                     type, balance, category, fingerprint)
                VALUES (?, ?, 'manual', ?, ?, ?, 'expense', NULL, ?, ?)
                """,
                (
                    expense["user_id"],
                    account_id,
                    expense["date"],
                    expense["memo"] or "手入力支出",
                    expense["amount"],
                    expense["category"],
                    f"manual:{expense['id']}",
                ),
            )
            transaction_id = cursor.lastrowid
        connection.execute(
            "UPDATE expenses SET transaction_id = ? WHERE id = ?",
            (transaction_id, expense["id"]),
        )


def migrate_budgets_schema(connection):
    """旧budgetsテーブルをユーザー別予算へ変換します。"""
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'budgets'"
    ).fetchone()
    if not exists:
        connection.execute(
            """
            CREATE TABLE budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                month TEXT NOT NULL,
                amount INTEGER NOT NULL CHECK (amount >= 0),
                UNIQUE(user_id, month),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        return
    if "user_id" in table_columns(connection, "budgets"):
        return

    connection.execute("ALTER TABLE budgets RENAME TO budgets_before_login")
    connection.execute(
        """
        CREATE TABLE budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            month TEXT NOT NULL,
            amount INTEGER NOT NULL CHECK (amount >= 0),
            UNIQUE(user_id, month),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        INSERT INTO budgets (user_id, month, amount)
        SELECT NULL, month, amount FROM budgets_before_login
        """
    )
    connection.execute("DROP TABLE budgets_before_login")


def migrate_legacy_expenses(connection):
    """既存のCSV支出データを所有者なしで一度だけ取り込みます。"""
    if not LEGACY_CSV_FILE.exists():
        return
    with LEGACY_CSV_FILE.open("r", newline="", encoding="utf-8-sig") as file:
        for record in csv.DictReader(file):
            try:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO expenses
                        (id, user_id, date, category, memo, amount)
                    VALUES (?, NULL, ?, ?, ?, ?)
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
    """既存のJSON予算データを所有者なしで一度だけ取り込みます。"""
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
                "INSERT INTO budgets (user_id, month, amount) VALUES (NULL, ?, ?)",
                (month, int(amount)),
            )
        except (TypeError, ValueError, sqlite3.IntegrityError):
            continue


def create_user(username, password_hash):
    """ユーザーを作成し、最初のユーザーには旧データを引き継ぎます。"""
    initialize_database()
    try:
        with connect() as connection:
            cursor = connection.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, password_hash),
            )
            user_id = cursor.lastrowid
            user_count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if user_count == 1:
                connection.execute(
                    "UPDATE expenses SET user_id = ? WHERE user_id IS NULL", (user_id,)
                )
                connection.execute(
                    "UPDATE budgets SET user_id = ? WHERE user_id IS NULL", (user_id,)
                )
                sync_unlinked_expenses(connection, user_id)
            return get_user_by_id(user_id, connection)
    except sqlite3.IntegrityError:
        return None


def get_user_by_id(user_id, connection=None):
    """IDでユーザーを取得します。"""
    initialize_database() if connection is None else None
    owns_connection = connection is None
    connection = connection or connect()
    try:
        row = connection.execute(
            "SELECT id, username, password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        if owns_connection:
            connection.close()


def get_user_by_username(username):
    """ユーザー名でユーザーを取得します。"""
    initialize_database()
    with connect() as connection:
        row = connection.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None


def user_filter(user_id):
    """ユーザーIDに応じたSQL条件と値を返します。"""
    return ("user_id IS NULL", ()) if user_id is None else ("user_id = ?", (user_id,))


def get_expenses(month=None, user_id=None):
    """指定ユーザーの支出を新しい順に取得します。"""
    initialize_database()
    condition, parameters = user_filter(user_id)
    query = f"SELECT id, date, category, memo, amount FROM expenses WHERE {condition}"
    parameters = list(parameters)
    if month:
        query += " AND date LIKE ?"
        parameters.append(f"{month}-%")
    query += " ORDER BY date DESC, id DESC"
    with connect() as connection:
        return [dict(row) for row in connection.execute(query, parameters).fetchall()]


def add_expense(date, category, memo, amount, user_id=None):
    """指定ユーザーへ支出を1件追加します。"""
    initialize_database()
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO expenses (user_id, date, category, memo, amount)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, date, category, memo, amount),
        )
        if user_id is not None:
            account_id = get_or_create_account(
                connection, user_id, "manual", "manual:default", "手入力"
            )
            transaction_cursor = connection.execute(
                """
                INSERT INTO transactions
                    (user_id, account_id, source, date, description, amount,
                     type, balance, category, fingerprint)
                VALUES (?, ?, 'manual', ?, ?, ?, 'expense', NULL, ?, ?)
                """,
                (
                    user_id,
                    account_id,
                    date,
                    memo or "手入力支出",
                    amount,
                    category,
                    f"manual:{cursor.lastrowid}",
                ),
            )
            connection.execute(
                "UPDATE expenses SET transaction_id = ? WHERE id = ?",
                (transaction_cursor.lastrowid, cursor.lastrowid),
            )
        expense_id = cursor.lastrowid
    clear_aggregate_cache()
    return expense_id


def import_expenses(records, user_id):
    """検証済みの複数支出を1トランザクションで登録します。"""
    initialize_database()
    with connect() as connection:
        connection.executemany(
            """
            INSERT INTO expenses (user_id, date, category, memo, amount)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    user_id,
                    record["date"],
                    record["category"],
                    record.get("memo", ""),
                    int(record["amount"]),
                )
                for record in records
            ],
        )
        sync_unlinked_expenses(connection, user_id)
    clear_aggregate_cache()
    return len(records)


def transaction_fingerprint(source, transaction):
    """同じ取引を判定するための安定したハッシュを作ります。"""
    transaction_type = transaction.get("type") or transaction.get("income_expense")
    values = [
        source,
        transaction["date"],
        transaction["description"].strip(),
        str(int(transaction["amount"])),
        transaction_type,
        "" if transaction.get("balance") is None else str(transaction["balance"]),
    ]
    return hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()


def import_bank_transactions(
    transactions,
    user_id,
    source,
    csv_type=None,
    bank=None,
    account_key=None,
    filename=None,
    parser_key=None,
    raw_csv=None,
    account_name=None,
):
    """銀行共通形式の取引を資産台帳へ追加します。"""
    initialize_database()
    imported = 0
    skipped = 0
    errors = 0
    income = 0
    expense = 0
    with connect() as connection:
        bank_name = bank or source
        account_key = account_key or f"{source}:default"
        account_id = get_or_create_account(
            connection,
            user_id,
            bank_name,
            account_key,
            account_name or f"{bank_name} 口座",
        )
        history_cursor = connection.execute(
            """
            INSERT INTO import_history
                (user_id, bank, csv_type, imported_count, skipped_count,
                 income_count, expense_count, filename, parser_key, raw_csv)
            VALUES (?, ?, ?, 0, 0, 0, 0, ?, ?, ?)
            """,
            (
                user_id,
                bank_name,
                csv_type or source,
                filename,
                parser_key or source,
                raw_csv,
            ),
        )
        history_id = history_cursor.lastrowid
        for transaction in transactions:
            try:
                transaction_type = transaction.get("type") or transaction.get(
                    "income_expense"
                )
                if transaction_type not in {"income", "expense"}:
                    raise ValueError("typeはincomeまたはexpenseが必要です")
                amount = int(transaction["amount"])
                if amount <= 0:
                    raise ValueError("amountは1以上が必要です")
                date = transaction["date"]
                description = transaction["description"].strip()
                category = transaction.get("category") or "その他"
                balance = transaction.get("balance")
                if not date or not description:
                    raise ValueError("dateとdescriptionは必須です")
                fingerprint = transaction_fingerprint(source, transaction)
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO transactions
                        (user_id, account_id, source, date, description, amount,
                         type, balance, category, fingerprint, import_history_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        account_id,
                        source,
                        date,
                        description,
                        amount,
                        transaction_type,
                        balance,
                        category,
                        fingerprint,
                        history_id,
                    ),
                )
                if cursor.rowcount == 0:
                    skipped += 1
                    continue
                imported += 1
                # Parserの一時データではなく、実際に保存したTransaction.typeを集計します。
                saved_type = connection.execute(
                    "SELECT type FROM transactions WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()["type"]
                if saved_type == "expense":
                    expense += 1
                    connection.execute(
                        """
                        INSERT INTO expenses
                            (user_id, transaction_id, date, category, memo, amount)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            user_id,
                            cursor.lastrowid,
                            date,
                            category,
                            description,
                            amount,
                        ),
                    )
                else:
                    income += 1
            except (KeyError, TypeError, ValueError, sqlite3.IntegrityError):
                errors += 1
        connection.execute(
            """
            UPDATE import_history
            SET imported_count = ?, skipped_count = ?, income_count = ?, expense_count = ?
            WHERE id = ?
            """,
            (imported, skipped, income, expense, history_id),
        )
        refresh_account_balance(connection, account_id)
    clear_aggregate_cache()
    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "income": income,
        "expense": expense,
    }


def get_import_history(user_id, limit=100):
    """ログインユーザーのCSVインポート履歴を新しい順で返します。"""
    initialize_database()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, imported_at, bank, csv_type, imported_count, skipped_count,
                   income_count, expense_count, filename, parser_key,
                   raw_csv IS NOT NULL AS can_reimport,
                   EXISTS(
                       SELECT 1 FROM transactions t WHERE t.import_history_id = import_history.id
                   ) AS can_undo
            FROM import_history
            WHERE user_id = ?
            ORDER BY imported_at DESC, id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def get_import_record(history_id, user_id):
    """再インポート用の履歴を所有者に限定して取得します。"""
    initialize_database()
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id, bank, csv_type, filename, parser_key, raw_csv
            FROM import_history WHERE id = ? AND user_id = ?
            """,
            (history_id, user_id),
        ).fetchone()
        return dict(row) if row else None


def delete_import_history(history_id, user_id):
    """履歴とそのCSVが新規登録した取引だけを取り消します。"""
    initialize_database()
    with connect() as connection:
        history = connection.execute(
            "SELECT id FROM import_history WHERE id = ? AND user_id = ?",
            (history_id, user_id),
        ).fetchone()
        if not history:
            return None
        rows = connection.execute(
            """
            SELECT id, account_id FROM transactions
            WHERE import_history_id = ? AND user_id = ?
            """,
            (history_id, user_id),
        ).fetchall()
        transaction_ids = [row["id"] for row in rows]
        account_ids = {row["account_id"] for row in rows if row["account_id"] is not None}
        if transaction_ids:
            placeholders = ",".join("?" for _ in transaction_ids)
            connection.execute(
                f"DELETE FROM expenses WHERE transaction_id IN ({placeholders})",
                transaction_ids,
            )
            connection.execute(
                f"DELETE FROM transactions WHERE id IN ({placeholders}) AND user_id = ?",
                (*transaction_ids, user_id),
            )
        connection.execute(
            "DELETE FROM import_history WHERE id = ? AND user_id = ?",
            (history_id, user_id),
        )
        for account_id in account_ids:
            refresh_account_balance(connection, account_id)
    clear_aggregate_cache()
    return {"transactions": len(transaction_ids)}


@lru_cache(maxsize=256)
def get_asset_dashboard(user_id, selected_month, months=12):
    """口座別資産と月末残高の推移を返します。"""
    initialize_database()
    year, month = (int(value) for value in selected_month.split("-"))
    month_keys = []
    for offset in range(months - 1, -1, -1):
        total_month = year * 12 + month - 1 - offset
        month_keys.append(f"{total_month // 12:04d}-{total_month % 12 + 1:02d}")
    with connect() as connection:
        accounts = [
            dict(row)
            for row in connection.execute(
                """
                SELECT id, institution, name, current_balance FROM accounts
                WHERE user_id = ? ORDER BY institution, id
                """,
                (user_id,),
            ).fetchall()
        ]
        balance_rows = connection.execute(
            """
            SELECT account_id, date, balance, id FROM transactions
            WHERE user_id = ? AND balance IS NOT NULL
            ORDER BY date, id
            """,
            (user_id,),
        ).fetchall()
    bank_assets = []
    cash = 0
    investments = 0
    total_assets = 0
    for account in accounts:
        balance = account["current_balance"] or 0
        label = f"{account['institution']} {account['name']}".upper()
        if "投資" in label or "SECUR" in label:
            investments += balance
        elif "現金" in label or account["institution"] == "cash":
            cash += balance
        elif account["current_balance"] is not None:
            bank_assets.append(account)
        total_assets += balance
    trend = []
    for month_key in month_keys:
        latest = {}
        for row in balance_rows:
            if row["date"][:7] <= month_key:
                latest[row["account_id"]] = row["balance"]
        trend.append(sum(latest.values()))
    return {
        "bank_assets": bank_assets,
        "cash_asset": cash,
        "investment_asset": investments,
        "total_assets": total_assets,
        "asset_chart": {"labels": month_keys, "values": trend},
    }


@lru_cache(maxsize=128)
def get_lifetime_statistics(user_id):
    """全Transactionから累計統計と月別収支・資産推移を作ります。"""
    initialize_database()
    with connect() as connection:
        totals = connection.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0)
                    AS total_income,
                COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0)
                    AS total_expense,
                COUNT(*) AS transaction_count,
                MIN(substr(date, 1, 7)) AS first_month,
                MAX(substr(date, 1, 7)) AS last_month
            FROM transactions WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        monthly_rows = connection.execute(
            """
            SELECT substr(date, 1, 7) AS month,
                   SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) AS income,
                   SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) AS expense
            FROM transactions WHERE user_id = ?
            GROUP BY substr(date, 1, 7) ORDER BY month
            """,
            (user_id,),
        ).fetchall()
        balance_rows = connection.execute(
            """
            SELECT account_id, date, balance, id FROM transactions
            WHERE user_id = ? AND balance IS NOT NULL ORDER BY date, id
            """,
            (user_id,),
        ).fetchall()
        current_assets = connection.execute(
            "SELECT COALESCE(SUM(current_balance), 0) FROM accounts WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]

    month_keys = []
    if totals["first_month"] and totals["last_month"]:
        first_year, first_month = (int(value) for value in totals["first_month"].split("-"))
        last_year, last_month = (int(value) for value in totals["last_month"].split("-"))
        first_index = first_year * 12 + first_month - 1
        last_index = last_year * 12 + last_month - 1
        month_keys = [
            f"{index // 12:04d}-{index % 12 + 1:02d}"
            for index in range(first_index, last_index + 1)
        ]
    monthly_by_key = {row["month"]: row for row in monthly_rows}
    incomes = [int(monthly_by_key.get(key, {"income": 0})["income"] or 0) for key in month_keys]
    expenses = [int(monthly_by_key.get(key, {"expense": 0})["expense"] or 0) for key in month_keys]
    nets = [income - expense for income, expense in zip(incomes, expenses)]
    asset_values = []
    for month_key in month_keys:
        latest = {}
        for row in balance_rows:
            if row["date"][:7] <= month_key:
                latest[row["account_id"]] = row["balance"]
        asset_values.append(sum(latest.values()))
    month_count = len(month_keys)
    total_income = int(totals["total_income"])
    total_expense = int(totals["total_expense"])
    return {
        "lifetime_stats": {
            "total_income": total_income,
            "total_expense": total_expense,
            "lifetime_net": total_income - total_expense,
            "current_assets": int(current_assets),
            "transaction_count": int(totals["transaction_count"]),
            "average_monthly_income": round(total_income / month_count) if month_count else 0,
            "average_monthly_expense": round(total_expense / month_count) if month_count else 0,
            "highest_balance": max(asset_values) if asset_values else 0,
            "lowest_balance": min(asset_values) if asset_values else 0,
        },
        "cashflow_chart": {
            "labels": month_keys,
            "income": incomes,
            "expense": expenses,
            "net": nets,
        },
        "lifetime_asset_chart": {
            "labels": month_keys,
            "previous": [asset_values[index - 1] if index else 0 for index in range(len(asset_values))],
            "values": asset_values,
            "carryover": list(asset_values),
        },
    }


@lru_cache(maxsize=128)
def get_category_ranking(user_id):
    """全期間の支出カテゴリを金額順で返します。"""
    initialize_database()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT category, SUM(amount) AS amount, COUNT(*) AS count
            FROM transactions
            WHERE user_id = ? AND type = 'expense'
            GROUP BY category ORDER BY amount DESC, category
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]


@lru_cache(maxsize=128)
def get_annual_reports(user_id):
    """年ごとの収入・支出・貯蓄率と前年比を返します。"""
    initialize_database()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT substr(date, 1, 4) AS year,
                   SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) AS income,
                   SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) AS expense
            FROM transactions WHERE user_id = ?
            GROUP BY substr(date, 1, 4) ORDER BY year
            """,
            (user_id,),
        ).fetchall()
    reports = []
    previous = None
    for row in rows:
        income = int(row["income"] or 0)
        expense = int(row["expense"] or 0)
        net = income - expense
        report = {
            "year": row["year"],
            "income": income,
            "expense": expense,
            "savings": max(net, 0),
            "savings_rate": (net / income * 100) if income else 0,
            "net": net,
            "previous_net": previous["net"] if previous else None,
            "net_change": (net - previous["net"]) if previous else None,
            "net_change_percent": (
                (net - previous["net"]) / abs(previous["net"]) * 100
                if previous and previous["net"]
                else None
            ),
        }
        reports.append(report)
        previous = report
    return list(reversed(reports))


def search_transactions(user_id, query="", filter_kind="", category="", bank=""):
    """取引を部分一致検索し、種別・カテゴリ・銀行で絞り込みます。"""
    initialize_database()
    sql = """
        SELECT t.id, t.date, t.description, t.amount, t.type, t.balance,
               t.category, t.source, a.institution AS bank, a.name AS account_name
        FROM transactions t
        LEFT JOIN accounts a ON a.id = t.account_id
        WHERE t.user_id = ?
    """
    parameters = [user_id]
    if query:
        term = f"%{query.strip()}%"
        sql += """
            AND (t.date LIKE ? OR t.description LIKE ? OR t.category LIKE ?
                 OR CAST(t.amount AS TEXT) LIKE ? OR COALESCE(a.institution, '') LIKE ?)
        """
        parameters.extend([term] * 5)
    if filter_kind in {"income", "expense"}:
        sql += " AND t.type = ?"
        parameters.append(filter_kind)
    elif filter_kind == "transfer":
        sql += " AND t.description LIKE '%振込%'"
    elif filter_kind == "card":
        sql += " AND (t.description LIKE '%カード%' OR t.description LIKE '%VISA%' OR t.description LIKE '%デビット%')"
    elif filter_kind == "cash":
        sql += " AND (t.source = 'manual' OR t.description LIKE '%ATM%')"
    if category:
        sql += " AND t.category = ?"
        parameters.append(category)
    if bank:
        sql += " AND a.institution = ?"
        parameters.append(bank)
    sql += " ORDER BY t.date DESC, t.id DESC LIMIT 1000"
    with connect() as connection:
        return [dict(row) for row in connection.execute(sql, parameters).fetchall()]


def get_financial_summary(user_id, month):
    """資産台帳から残高、月次収支、翌月繰越を計算します。"""
    initialize_database()
    month_start = f"{month}-01"
    with connect() as connection:
        balance_row = connection.execute(
            """
            SELECT SUM(current_balance) AS total FROM accounts
            WHERE user_id = ? AND current_balance IS NOT NULL
            """,
            (user_id,),
        ).fetchone()
        current_balance = balance_row["total"]
        income = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0) FROM transactions
            WHERE user_id = ? AND type = 'income' AND date LIKE ?
            """,
            (user_id, f"{month}-%"),
        ).fetchone()[0]
        expense = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0) FROM transactions
            WHERE user_id = ? AND type = 'expense' AND date LIKE ?
            """,
            (user_id, f"{month}-%"),
        ).fetchone()[0]
        opening_row = connection.execute(
            """
            SELECT SUM(balance) FROM (
                SELECT balance,
                       ROW_NUMBER() OVER (
                           PARTITION BY account_id ORDER BY date DESC, id DESC
                       ) AS row_number
                FROM transactions
                WHERE user_id = ? AND balance IS NOT NULL AND date < ?
            ) WHERE row_number = 1
            """,
            (user_id, month_start),
        ).fetchone()[0]
        closing_row = connection.execute(
            """
            SELECT SUM(balance) FROM (
                SELECT balance,
                       ROW_NUMBER() OVER (
                           PARTITION BY account_id ORDER BY date DESC, id DESC
                       ) AS row_number
                FROM transactions
                WHERE user_id = ? AND balance IS NOT NULL
                  AND date < date(?, '+1 month')
            ) WHERE row_number = 1
            """,
            (user_id, month_start),
        ).fetchone()[0]
        monthly_net = income - expense
        if opening_row is not None:
            previous_balance = opening_row
        elif closing_row is not None:
            previous_balance = closing_row - monthly_net
        else:
            previous_balance = 0
        return {
            "current_balance": current_balance,
            "monthly_income": income,
            "monthly_expense": expense,
            "monthly_net": monthly_net,
            "previous_balance": previous_balance,
            "carried_balance": previous_balance + monthly_net,
        }


def get_account_balances(user_id):
    """ユーザーが持つ口座ごとの現在残高を返します。"""
    initialize_database()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT institution, account_key, name, current_balance
            FROM accounts WHERE user_id = ? ORDER BY institution, id
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def reset_user_data(user_id):
    """ユーザーを残し、そのユーザーの取引・履歴・重複判定を削除します。"""
    initialize_database()
    with connect() as connection:
        expense_count = connection.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        transaction_count = connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        history_count = connection.execute(
            "SELECT COUNT(*) FROM import_history WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        connection.execute("DELETE FROM expenses WHERE user_id = ?", (user_id,))
        # transactionsを消すとfingerprintの重複判定もリセットされます。
        connection.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
        connection.execute("DELETE FROM import_history WHERE user_id = ?", (user_id,))
        connection.execute(
            "UPDATE accounts SET current_balance = NULL WHERE user_id = ?", (user_id,)
        )
        result = {
            "expenses": expense_count,
            "transactions": transaction_count,
            "history": history_count,
        }
    clear_aggregate_cache()
    return result


def delete_expense(expense_id, user_id=None):
    """指定ユーザーが所有する支出だけを削除します。"""
    initialize_database()
    condition, parameters = user_filter(user_id)
    with connect() as connection:
        row = connection.execute(
            f"SELECT transaction_id FROM expenses WHERE id = ? AND {condition}",
            (expense_id, *parameters),
        ).fetchone()
        cursor = connection.execute(
            f"DELETE FROM expenses WHERE id = ? AND {condition}",
            (expense_id, *parameters),
        )
        if row and row["transaction_id"]:
            transaction = connection.execute(
                "SELECT account_id FROM transactions WHERE id = ?",
                (row["transaction_id"],),
            ).fetchone()
            connection.execute(
                "DELETE FROM transactions WHERE id = ?", (row["transaction_id"],)
            )
            if transaction and transaction["account_id"]:
                refresh_account_balance(connection, transaction["account_id"])
        deleted = cursor.rowcount > 0
    clear_aggregate_cache()
    return deleted


def replace_expenses(records):
    """デスクトップ版の所有者なし支出を全て置き換えます。"""
    initialize_database()
    with connect() as connection:
        connection.execute("DELETE FROM expenses WHERE user_id IS NULL")
        connection.executemany(
            """
            INSERT INTO expenses (user_id, date, category, memo, amount)
            VALUES (NULL, ?, ?, ?, ?)
            """,
            [
                (
                    record["date"],
                    record["category"],
                    record.get("memo", ""),
                    int(record["amount"]),
                )
                for record in records
            ],
        )


def get_budgets(user_id=None):
    """指定ユーザーの月別予算を辞書で返します。"""
    initialize_database()
    condition, parameters = user_filter(user_id)
    with connect() as connection:
        rows = connection.execute(
            f"SELECT month, amount FROM budgets WHERE {condition}", parameters
        ).fetchall()
        return {row["month"]: row["amount"] for row in rows}


def set_month_budget(month, amount, user_id=None):
    """指定ユーザーの月別予算を追加または更新します。"""
    initialize_database()
    with connect() as connection:
        if user_id is None:
            connection.execute(
                "DELETE FROM budgets WHERE user_id IS NULL AND month = ?", (month,)
            )
            connection.execute(
                "INSERT INTO budgets (user_id, month, amount) VALUES (NULL, ?, ?)",
                (month, amount),
            )
        else:
            connection.execute(
                """
                INSERT INTO budgets (user_id, month, amount) VALUES (?, ?, ?)
                ON CONFLICT(user_id, month) DO UPDATE SET amount = excluded.amount
                """,
                (user_id, month, amount),
            )
