"""EQUAのSQLite / PostgreSQL共通SQLAlchemyデータ層。"""

import csv
import hashlib
import json
import os
import sqlite3
import sys
from functools import lru_cache
from pathlib import Path

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    and_,
    case,
    cast,
    create_engine,
    delete,
    func,
    inspect,
    or_,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from utils.datetime import utc_now_string


def get_data_directory():
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


DATABASE_FILE = get_data_directory() / "local.db"
LEGACY_DATABASE_FILE = get_data_directory() / "kakeibo.db"
LEGACY_CSV_FILE = get_data_directory() / "kakeibo.csv"
LEGACY_BUDGET_FILE = get_data_directory() / "budgets.json"


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)


class AccountModel(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("user_id", "account_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    institution: Mapped[str] = mapped_column(String(150), nullable=False)
    account_key: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    current_balance: Mapped[int | None] = mapped_column(BigInteger)


class ImportHistoryModel(Base):
    __tablename__ = "import_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    imported_at: Mapped[str] = mapped_column(String(32), default=utc_now_string, nullable=False)
    bank: Mapped[str] = mapped_column(String(150), default="不明", nullable=False)
    csv_type: Mapped[str] = mapped_column(String(200), nullable=False)
    imported_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    income_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expense_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    filename: Mapped[str | None] = mapped_column(String(500))
    parser_key: Mapped[str | None] = mapped_column(String(100))
    raw_csv: Mapped[bytes | None] = mapped_column(LargeBinary)


class TransactionModel(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("user_id", "fingerprint"),
        Index("idx_transactions_user_date", "user_id", "date"),
        Index("idx_transactions_account_date", "account_id", "date"),
        Index("idx_transactions_import_history", "import_history_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    import_history_id: Mapped[int | None] = mapped_column(ForeignKey("import_history.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    date: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    balance: Mapped[int | None] = mapped_column(BigInteger)
    category: Mapped[str] = mapped_column(String(100), default="その他", nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now_string, nullable=False)


class ExpenseModel(Base):
    __tablename__ = "expenses"
    __table_args__ = (Index("idx_expenses_user_date", "user_id", "date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"))
    date: Mapped[str] = mapped_column(String(10), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    memo: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)


class BudgetModel(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("user_id", "month"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)


_engine = None
_engine_key = None
_Session = None
_engine_file_identity = None


def get_database_url():
    """DATABASE_URLがあればPostgreSQL、なければlocal.dbを返します。"""
    configured = os.environ.get("DATABASE_URL", "").strip()
    if configured:
        if configured.startswith("postgres://"):
            configured = "postgresql+psycopg://" + configured[len("postgres://") :]
        elif configured.startswith("postgresql://"):
            configured = "postgresql+psycopg://" + configured[len("postgresql://") :]
        return configured
    if os.environ.get("RENDER", "").lower() == "true":
        raise RuntimeError(
            "Render本番環境にDATABASE_URLが設定されていません。"
            "SQLiteへのフォールバックはデータ消失を防ぐため無効です。"
        )
    return f"sqlite:///{DATABASE_FILE.resolve()}"


def get_engine():
    global _engine, _engine_key, _Session, _engine_file_identity
    url = get_database_url()
    file_identity = None
    if url.startswith("sqlite"):
        try:
            stat = DATABASE_FILE.stat()
            file_identity = (stat.st_dev, stat.st_ino)
        except FileNotFoundError:
            pass
    if _engine is None or _engine_key != url or (
        url.startswith("sqlite") and _engine_file_identity != file_identity
    ):
        if _engine is not None:
            _engine.dispose()
        options = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            options["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **options)
        _engine_key = url
        _engine_file_identity = file_identity
        _Session = sessionmaker(bind=_engine, expire_on_commit=False)
        clear_aggregate_cache()
    return _engine


def get_session():
    get_engine()
    return _Session()


def is_postgresql():
    return get_engine().dialect.name == "postgresql"


def get_database_status():
    """パスワードを含めず、接続先と主要データ件数を診断用に返します。"""
    engine = get_engine()
    schema = inspect(engine)
    counts = {}
    with engine.connect() as connection:
        for table_name in ("users", "transactions", "accounts", "import_history", "budgets"):
            counts[table_name] = (
                connection.scalar(
                    select(func.count()).select_from(Base.metadata.tables[table_name])
                )
                if schema.has_table(table_name)
                else None
            )
    return {
        "backend": engine.dialect.name,
        "host": engine.url.host or "local",
        "database": engine.url.database or str(DATABASE_FILE),
        "counts": counts,
    }


def connect():
    """旧テスト/調査用のSQLite接続。アプリ本体はSQLAlchemyを使用します。"""
    if is_postgresql():
        return get_engine().raw_connection()
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def table_columns(connection, table_name):
    if get_engine().dialect.name == "sqlite" and isinstance(connection, sqlite3.Connection):
        return {row["name"] for row in connection.execute(f"PRAGMA table_info({table_name})")}
    return {column["name"] for column in inspect(get_engine()).get_columns(table_name)}


def _prepare_legacy_sqlite_schema():
    if get_engine().dialect.name != "sqlite" or not DATABASE_FILE.exists():
        return
    with sqlite3.connect(DATABASE_FILE) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "budgets" in tables:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(budgets)")}
            if "user_id" not in columns:
                connection.execute("ALTER TABLE budgets RENAME TO budgets_legacy")


def _add_missing_columns():
    engine = get_engine()
    schema = inspect(engine)
    additions = {
        "expenses": {"user_id": "INTEGER", "transaction_id": "INTEGER"},
        "transactions": {"import_history_id": "INTEGER"},
        "import_history": {
            "bank": "VARCHAR(150) DEFAULT '不明' NOT NULL",
            "income_count": "INTEGER DEFAULT 0 NOT NULL",
            "expense_count": "INTEGER DEFAULT 0 NOT NULL",
            "filename": "VARCHAR(500)",
            "parser_key": "VARCHAR(100)",
            "raw_csv": "BYTEA" if engine.dialect.name == "postgresql" else "BLOB",
        },
    }
    with engine.begin() as connection:
        for table_name, definitions in additions.items():
            if not schema.has_table(table_name):
                continue
            present = {column["name"] for column in schema.get_columns(table_name)}
            for column, definition in definitions.items():
                if column not in present:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column} {definition}"))


def initialize_database():
    """SQLAlchemyで全テーブルを作成し、旧SQLiteスキーマを保ったまま移行します。"""
    _prepare_legacy_sqlite_schema()
    Base.metadata.create_all(get_engine())
    _add_missing_columns()
    if get_engine().dialect.name == "sqlite":
        _migrate_legacy_budget_table()
        _migrate_legacy_bank_transactions()
        _migrate_legacy_files()
    _sync_unlinked_expenses()


def _migrate_legacy_budget_table():
    inspector = inspect(get_engine())
    if not inspector.has_table("budgets_legacy"):
        return
    with get_engine().begin() as connection:
        rows = connection.execute(text("SELECT month, amount FROM budgets_legacy")).mappings().all()
        existing = connection.execute(text("SELECT COUNT(*) FROM budgets")).scalar_one()
        if not existing:
            for row in rows:
                connection.execute(text("INSERT INTO budgets (user_id, month, amount) VALUES (NULL, :month, :amount)"), dict(row))
        connection.execute(text("DROP TABLE budgets_legacy"))


def _migrate_legacy_bank_transactions():
    inspector = inspect(get_engine())
    if not inspector.has_table("bank_transactions"):
        return
    with get_engine().connect() as connection:
        rows = connection.execute(text("SELECT * FROM bank_transactions ORDER BY id")).mappings().all()
    with get_session() as session, session.begin():
        for row in rows:
            account = _get_or_create_account(session, row["user_id"], row["source"], f"{row['source']}:default", f"{row['source']} 口座")
            if not session.scalar(select(TransactionModel.id).where(TransactionModel.user_id == row["user_id"], TransactionModel.fingerprint == row["fingerprint"])):
                session.add(TransactionModel(user_id=row["user_id"], account_id=account.id, source=row["source"], date=row["date"], description=row["description"], amount=row["amount"], type=row["income_expense"], balance=row["balance"], category=row["category"], fingerprint=row["fingerprint"], created_at=row.get("created_at") or utc_now_string()))
    with get_engine().begin() as connection:
        connection.execute(text("DROP TABLE bank_transactions"))
    _refresh_all_account_balances()


def _migrate_legacy_files():
    with get_session() as session:
        expense_count = session.scalar(select(func.count()).select_from(ExpenseModel))
        budget_count = session.scalar(select(func.count()).select_from(BudgetModel))
    if not expense_count and LEGACY_CSV_FILE.exists():
        try:
            with LEGACY_CSV_FILE.open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))
            with get_session() as session, session.begin():
                for row in rows:
                    session.add(ExpenseModel(id=int(row["id"]), date=row["date"], category=row["category"], memo=row.get("memo", ""), amount=int(row["amount"])))
        except (OSError, KeyError, TypeError, ValueError):
            pass
    if not budget_count and LEGACY_BUDGET_FILE.exists():
        try:
            with LEGACY_BUDGET_FILE.open(encoding="utf-8") as file:
                values = json.load(file)
            with get_session() as session, session.begin():
                for month, amount in values.items():
                    session.add(BudgetModel(month=month, amount=int(amount)))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass


def clear_aggregate_cache():
    for name in ("get_asset_dashboard", "get_lifetime_statistics", "get_category_ranking", "get_annual_reports"):
        function = globals().get(name)
        if function and hasattr(function, "cache_clear"):
            function.cache_clear()


def _model_dict(model, fields):
    return {field: getattr(model, field) for field in fields}


def _get_or_create_account(session, user_id, institution, account_key, name):
    account = session.scalar(select(AccountModel).where(AccountModel.user_id == user_id, AccountModel.account_key == account_key))
    if not account:
        account = AccountModel(user_id=user_id, institution=institution, account_key=account_key, name=name)
        session.add(account)
        session.flush()
    return account


def _refresh_account_balance(session, account_id):
    row = session.scalars(select(TransactionModel).where(TransactionModel.account_id == account_id, TransactionModel.balance.is_not(None)).order_by(TransactionModel.date.desc(), TransactionModel.id.desc()).limit(1)).first()
    account = session.get(AccountModel, account_id)
    if account:
        account.current_balance = row.balance if row else None


def _refresh_all_account_balances(user_id=None):
    with get_session() as session, session.begin():
        query = select(AccountModel.id)
        if user_id is not None:
            query = query.where(AccountModel.user_id == user_id)
        for account_id in session.scalars(query):
            _refresh_account_balance(session, account_id)


def _sync_unlinked_expenses(user_id=None):
    with get_session() as session, session.begin():
        query = select(ExpenseModel).where(ExpenseModel.transaction_id.is_(None), ExpenseModel.user_id.is_not(None))
        if user_id is not None:
            query = query.where(ExpenseModel.user_id == user_id)
        for expense in session.scalars(query):
            transaction = session.scalar(select(TransactionModel).where(TransactionModel.user_id == expense.user_id, TransactionModel.type == "expense", TransactionModel.date == expense.date, TransactionModel.amount == expense.amount, TransactionModel.description == expense.memo).limit(1))
            if not transaction:
                account = _get_or_create_account(session, expense.user_id, "manual", "manual:default", "手入力")
                transaction = TransactionModel(user_id=expense.user_id, account_id=account.id, source="manual", date=expense.date, description=expense.memo or "手入力支出", amount=expense.amount, type="expense", category=expense.category, fingerprint=f"manual:{expense.id}")
                session.add(transaction)
                session.flush()
            expense.transaction_id = transaction.id


def create_user(username, password_hash):
    initialize_database()
    with get_session() as session:
        if session.scalar(select(UserModel.id).where(func.lower(UserModel.username) == username.lower())):
            return None
        try:
            user = UserModel(username=username, password_hash=password_hash)
            session.add(user)
            session.flush()
            if session.scalar(select(func.count()).select_from(UserModel)) == 1:
                session.execute(ExpenseModel.__table__.update().where(ExpenseModel.user_id.is_(None)).values(user_id=user.id))
                session.execute(BudgetModel.__table__.update().where(BudgetModel.user_id.is_(None)).values(user_id=user.id))
            session.commit()
            result = _model_dict(user, ("id", "username", "password_hash"))
        except Exception:
            session.rollback()
            return None
    _sync_unlinked_expenses(result["id"])
    return result


def get_user_by_id(user_id, connection=None):
    initialize_database()
    with get_session() as session:
        user = session.get(UserModel, user_id)
        return _model_dict(user, ("id", "username", "password_hash")) if user else None


def get_user_by_username(username):
    initialize_database()
    with get_session() as session:
        user = session.scalar(select(UserModel).where(func.lower(UserModel.username) == username.lower()))
        return _model_dict(user, ("id", "username", "password_hash")) if user else None


def get_expenses(month=None, user_id=None):
    initialize_database()
    with get_session() as session:
        query = select(ExpenseModel).where(ExpenseModel.user_id == user_id if user_id is not None else ExpenseModel.user_id.is_(None))
        if month:
            query = query.where(ExpenseModel.date.like(f"{month}-%"))
        rows = session.scalars(query.order_by(ExpenseModel.date.desc(), ExpenseModel.id.desc())).all()
        return [_model_dict(row, ("id", "date", "category", "memo", "amount")) for row in rows]


def add_expense(date, category, memo, amount, user_id=None):
    initialize_database()
    with get_session() as session, session.begin():
        expense = ExpenseModel(user_id=user_id, date=date, category=category, memo=memo, amount=amount)
        session.add(expense)
        session.flush()
        if user_id is not None:
            account = _get_or_create_account(session, user_id, "manual", "manual:default", "手入力")
            transaction = TransactionModel(user_id=user_id, account_id=account.id, source="manual", date=date, description=memo or "手入力支出", amount=amount, type="expense", category=category, fingerprint=f"manual:{expense.id}")
            session.add(transaction)
            session.flush()
            expense.transaction_id = transaction.id
        expense_id = expense.id
    clear_aggregate_cache()
    return expense_id


def import_expenses(records, user_id):
    for record in records:
        add_expense(record["date"], record["category"], record.get("memo", ""), int(record["amount"]), user_id)
    return len(records)


def transaction_fingerprint(source, transaction):
    kind = transaction.get("type") or transaction.get("income_expense")
    values = [source, transaction["date"], transaction["description"].strip(), str(int(transaction["amount"])), kind, "" if transaction.get("balance") is None else str(transaction["balance"])]
    return hashlib.sha256("\x1f".join(values).encode()).hexdigest()


def import_bank_transactions(transactions, user_id, source, csv_type=None, bank=None, account_key=None, filename=None, parser_key=None, raw_csv=None, account_name=None):
    initialize_database()
    result = {"imported": 0, "skipped": 0, "errors": 0, "income": 0, "expense": 0}
    with get_session() as session, session.begin():
        bank_name = bank or source
        account = _get_or_create_account(session, user_id, bank_name, account_key or f"{source}:default", account_name or f"{bank_name} 口座")
        history = ImportHistoryModel(user_id=user_id, bank=bank_name, csv_type=csv_type or source, filename=filename, parser_key=parser_key or source, raw_csv=raw_csv)
        session.add(history)
        session.flush()
        for item in transactions:
            try:
                kind = item.get("type") or item.get("income_expense")
                amount = int(item["amount"])
                description = item["description"].strip()
                if kind not in {"income", "expense"} or amount <= 0 or not item["date"] or not description:
                    raise ValueError
                fingerprint = transaction_fingerprint(source, item)
                if session.scalar(select(TransactionModel.id).where(TransactionModel.user_id == user_id, TransactionModel.fingerprint == fingerprint)):
                    result["skipped"] += 1
                    continue
                transaction = TransactionModel(user_id=user_id, account_id=account.id, import_history_id=history.id, source=source, date=item["date"], description=description, amount=amount, type=kind, balance=item.get("balance"), category=item.get("category") or "その他", fingerprint=fingerprint)
                session.add(transaction)
                session.flush()
                result["imported"] += 1
                result[kind] += 1
                if kind == "expense":
                    session.add(ExpenseModel(user_id=user_id, transaction_id=transaction.id, date=transaction.date, category=transaction.category, memo=description, amount=amount))
            except (KeyError, TypeError, ValueError):
                result["errors"] += 1
        history.imported_count = result["imported"]
        history.skipped_count = result["skipped"]
        history.income_count = result["income"]
        history.expense_count = result["expense"]
        _refresh_account_balance(session, account.id)
    clear_aggregate_cache()
    return result


def get_import_history(user_id, limit=100):
    initialize_database()
    with get_session() as session:
        rows = session.scalars(select(ImportHistoryModel).where(ImportHistoryModel.user_id == user_id).order_by(ImportHistoryModel.imported_at.desc(), ImportHistoryModel.id.desc()).limit(limit)).all()
        output = []
        for row in rows:
            values = _model_dict(row, ("id", "imported_at", "bank", "csv_type", "imported_count", "skipped_count", "income_count", "expense_count", "filename", "parser_key"))
            values["can_reimport"] = row.raw_csv is not None
            values["can_undo"] = bool(session.scalar(select(TransactionModel.id).where(TransactionModel.import_history_id == row.id).limit(1)))
            output.append(values)
        return output


def get_import_record(history_id, user_id):
    initialize_database()
    with get_session() as session:
        row = session.scalar(select(ImportHistoryModel).where(ImportHistoryModel.id == history_id, ImportHistoryModel.user_id == user_id))
        return _model_dict(row, ("id", "bank", "csv_type", "filename", "parser_key", "raw_csv")) if row else None


def delete_import_history(history_id, user_id):
    initialize_database()
    with get_session() as session, session.begin():
        history = session.scalar(select(ImportHistoryModel).where(ImportHistoryModel.id == history_id, ImportHistoryModel.user_id == user_id))
        if not history:
            return None
        transactions = session.scalars(select(TransactionModel).where(TransactionModel.import_history_id == history_id, TransactionModel.user_id == user_id)).all()
        account_ids = {row.account_id for row in transactions if row.account_id}
        ids = [row.id for row in transactions]
        if ids:
            session.execute(delete(ExpenseModel).where(ExpenseModel.transaction_id.in_(ids)))
            session.execute(delete(TransactionModel).where(TransactionModel.id.in_(ids)))
        session.delete(history)
        session.flush()
        for account_id in account_ids:
            _refresh_account_balance(session, account_id)
    clear_aggregate_cache()
    return {"transactions": len(ids)}


def _all_transactions(session, user_id):
    return session.scalars(select(TransactionModel).where(TransactionModel.user_id == user_id).order_by(TransactionModel.date, TransactionModel.id)).all()


def _month_keys(rows):
    if not rows:
        return []
    first = min(row.date[:7] for row in rows)
    last = max(row.date[:7] for row in rows)
    fy, fm = map(int, first.split("-")); ly, lm = map(int, last.split("-"))
    return [f"{index // 12:04d}-{index % 12 + 1:02d}" for index in range(fy * 12 + fm - 1, ly * 12 + lm)]


def _asset_values(rows, months):
    values = []
    for month in months:
        latest = {}
        for row in rows:
            if row.balance is not None and row.date[:7] <= month:
                latest[row.account_id] = row.balance
        values.append(sum(latest.values()))
    return values


@lru_cache(maxsize=256)
def get_asset_dashboard(user_id, selected_month, months=12):
    initialize_database()
    year, month = map(int, selected_month.split("-"))
    keys = []
    for offset in range(months - 1, -1, -1):
        index = year * 12 + month - 1 - offset
        keys.append(f"{index // 12:04d}-{index % 12 + 1:02d}")
    with get_session() as session:
        accounts = session.scalars(select(AccountModel).where(AccountModel.user_id == user_id).order_by(AccountModel.institution, AccountModel.id)).all()
        rows = _all_transactions(session, user_id)
    bank_assets, cash, investments, total = [], 0, 0, 0
    for account in accounts:
        balance = account.current_balance or 0
        label = f"{account.institution} {account.name}".upper()
        data = _model_dict(account, ("id", "institution", "name", "current_balance"))
        if "投資" in label or "SECUR" in label: investments += balance
        elif "現金" in label or account.institution == "cash": cash += balance
        elif account.current_balance is not None: bank_assets.append(data)
        total += balance
    return {"bank_assets": bank_assets, "cash_asset": cash, "investment_asset": investments, "total_assets": total, "asset_chart": {"labels": keys, "values": _asset_values(rows, keys)}}


@lru_cache(maxsize=128)
def get_lifetime_statistics(user_id):
    initialize_database()
    with get_session() as session:
        rows = _all_transactions(session, user_id)
        current_assets = session.scalar(select(func.coalesce(func.sum(AccountModel.current_balance), 0)).where(AccountModel.user_id == user_id)) or 0
    months = _month_keys(rows)
    income = [sum(row.amount for row in rows if row.type == "income" and row.date[:7] == month) for month in months]
    expense = [sum(row.amount for row in rows if row.type == "expense" and row.date[:7] == month) for month in months]
    assets = _asset_values(rows, months)
    total_income, total_expense = sum(income), sum(expense)
    return {"lifetime_stats": {"total_income": total_income, "total_expense": total_expense, "lifetime_net": total_income - total_expense, "current_assets": int(current_assets), "transaction_count": len(rows), "average_monthly_income": round(total_income / len(months)) if months else 0, "average_monthly_expense": round(total_expense / len(months)) if months else 0, "highest_balance": max(assets) if assets else 0, "lowest_balance": min(assets) if assets else 0}, "cashflow_chart": {"labels": months, "income": income, "expense": expense, "net": [a - b for a, b in zip(income, expense)]}, "lifetime_asset_chart": {"labels": months, "previous": [assets[index - 1] if index else 0 for index in range(len(assets))], "values": assets, "carryover": list(assets), "has_data": any(row.balance is not None for row in rows)}}


@lru_cache(maxsize=128)
def get_category_ranking(user_id):
    initialize_database()
    with get_session() as session:
        rows = session.execute(select(TransactionModel.category, func.sum(TransactionModel.amount).label("amount"), func.count(TransactionModel.id).label("count")).where(TransactionModel.user_id == user_id, TransactionModel.type == "expense").group_by(TransactionModel.category).order_by(func.sum(TransactionModel.amount).desc(), TransactionModel.category)).all()
        return [{"category": row.category, "amount": int(row.amount), "count": row.count} for row in rows]


@lru_cache(maxsize=128)
def get_annual_reports(user_id):
    initialize_database()
    with get_session() as session:
        rows = _all_transactions(session, user_id)
    years = {}
    for row in rows:
        values = years.setdefault(row.date[:4], {"income": 0, "expense": 0})
        values[row.type] += row.amount
    reports, previous = [], None
    for year in sorted(years):
        income, expense = years[year]["income"], years[year]["expense"]
        net = income - expense
        report = {"year": year, "income": income, "expense": expense, "savings": max(net, 0), "savings_rate": net / income * 100 if income else 0, "net": net, "previous_net": previous["net"] if previous else None, "net_change": net - previous["net"] if previous else None, "net_change_percent": (net - previous["net"]) / abs(previous["net"]) * 100 if previous and previous["net"] else None}
        reports.append(report); previous = report
    return list(reversed(reports))


def search_transactions(user_id, query="", filter_kind="", category="", bank=""):
    initialize_database()
    with get_session() as session:
        statement = select(TransactionModel, AccountModel).outerjoin(AccountModel, AccountModel.id == TransactionModel.account_id).where(TransactionModel.user_id == user_id)
        if query:
            term = f"%{query.strip()}%"
            statement = statement.where(or_(TransactionModel.date.like(term), TransactionModel.description.like(term), TransactionModel.category.like(term), cast(TransactionModel.amount, String).like(term), AccountModel.institution.like(term)))
        if filter_kind in {"income", "expense"}: statement = statement.where(TransactionModel.type == filter_kind)
        elif filter_kind == "transfer": statement = statement.where(TransactionModel.description.like("%振込%"))
        elif filter_kind == "card": statement = statement.where(or_(TransactionModel.description.like("%カード%"), TransactionModel.description.ilike("%visa%"), TransactionModel.description.like("%デビット%")))
        elif filter_kind == "cash": statement = statement.where(or_(TransactionModel.source == "manual", TransactionModel.description.ilike("%atm%")))
        if category: statement = statement.where(TransactionModel.category == category)
        if bank: statement = statement.where(AccountModel.institution == bank)
        output = []
        for transaction, account in session.execute(statement.order_by(TransactionModel.date.desc(), TransactionModel.id.desc()).limit(1000)):
            values = _model_dict(transaction, ("id", "date", "description", "amount", "type", "balance", "category", "source"))
            values.update(bank=account.institution if account else None, account_name=account.name if account else None)
            output.append(values)
        return output


def get_financial_summary(user_id, month):
    initialize_database()
    with get_session() as session:
        rows = _all_transactions(session, user_id)
        current = session.scalar(select(func.sum(AccountModel.current_balance)).where(AccountModel.user_id == user_id, AccountModel.current_balance.is_not(None)))
    income = sum(row.amount for row in rows if row.type == "income" and row.date[:7] == month)
    expense = sum(row.amount for row in rows if row.type == "expense" and row.date[:7] == month)
    opening = {}
    closing = {}
    for row in rows:
        if row.balance is None: continue
        if row.date[:7] < month: opening[row.account_id] = row.balance
        if row.date[:7] <= month: closing[row.account_id] = row.balance
    net = income - expense
    previous = sum(opening.values()) if opening else (sum(closing.values()) - net if closing else 0)
    return {"current_balance": current, "monthly_income": income, "monthly_expense": expense, "monthly_net": net, "previous_balance": previous, "carried_balance": previous + net}


def get_account_balances(user_id):
    initialize_database()
    with get_session() as session:
        rows = session.scalars(select(AccountModel).where(AccountModel.user_id == user_id).order_by(AccountModel.institution, AccountModel.id)).all()
        return [_model_dict(row, ("institution", "account_key", "name", "current_balance")) for row in rows]


def reset_user_data(user_id):
    initialize_database()
    with get_session() as session, session.begin():
        counts = {"expenses": session.scalar(select(func.count()).select_from(ExpenseModel).where(ExpenseModel.user_id == user_id)), "transactions": session.scalar(select(func.count()).select_from(TransactionModel).where(TransactionModel.user_id == user_id)), "history": session.scalar(select(func.count()).select_from(ImportHistoryModel).where(ImportHistoryModel.user_id == user_id))}
        session.execute(delete(ExpenseModel).where(ExpenseModel.user_id == user_id))
        session.execute(delete(TransactionModel).where(TransactionModel.user_id == user_id))
        session.execute(delete(ImportHistoryModel).where(ImportHistoryModel.user_id == user_id))
        session.execute(AccountModel.__table__.update().where(AccountModel.user_id == user_id).values(current_balance=None))
    clear_aggregate_cache(); return counts


def delete_expense(expense_id, user_id=None):
    initialize_database()
    with get_session() as session, session.begin():
        condition = ExpenseModel.user_id == user_id if user_id is not None else ExpenseModel.user_id.is_(None)
        expense = session.scalar(select(ExpenseModel).where(ExpenseModel.id == expense_id, condition))
        if not expense: return False
        transaction = session.get(TransactionModel, expense.transaction_id) if expense.transaction_id else None
        account_id = transaction.account_id if transaction else None
        session.delete(expense)
        if transaction: session.delete(transaction)
        session.flush()
        if account_id: _refresh_account_balance(session, account_id)
    clear_aggregate_cache(); return True


def replace_expenses(records):
    initialize_database()
    with get_session() as session, session.begin():
        session.execute(delete(ExpenseModel).where(ExpenseModel.user_id.is_(None)))
        session.add_all([ExpenseModel(date=row["date"], category=row["category"], memo=row.get("memo", ""), amount=int(row["amount"])) for row in records])
    clear_aggregate_cache()


def get_budgets(user_id=None):
    initialize_database()
    with get_session() as session:
        condition = BudgetModel.user_id == user_id if user_id is not None else BudgetModel.user_id.is_(None)
        return {row.month: row.amount for row in session.scalars(select(BudgetModel).where(condition))}


def set_month_budget(month, amount, user_id=None):
    initialize_database()
    with get_session() as session, session.begin():
        condition = BudgetModel.user_id == user_id if user_id is not None else BudgetModel.user_id.is_(None)
        budget = session.scalar(select(BudgetModel).where(condition, BudgetModel.month == month))
        if budget: budget.amount = amount
        else: session.add(BudgetModel(user_id=user_id, month=month, amount=amount))
