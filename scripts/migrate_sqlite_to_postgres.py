#!/usr/bin/env python3
"""EQUAのSQLite全テーブルをPostgreSQLへ移行するスクリプト。"""

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, delete, func, inspect, select, text

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from database import Base  # noqa: E402


TABLE_ORDER = (
    "users",
    "accounts",
    "import_history",
    "transactions",
    "expenses",
    "budgets",
)
DEFAULT_SOURCE = (
    PROJECT_DIR / "local.db"
    if (PROJECT_DIR / "local.db").exists()
    else PROJECT_DIR / "kakeibo.db"
)


def normalize_postgres_url(url):
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def migrate(source_path, target_url, replace=False):
    source_path = Path(source_path).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"SQLiteファイルが見つかりません: {source_path}")
    target_url = normalize_postgres_url(target_url)
    if not target_url.startswith("postgresql+psycopg://"):
        raise ValueError("移行先にPostgreSQLのDATABASE_URLを指定してください")

    source = create_engine(f"sqlite:///{source_path}")
    target = create_engine(target_url, pool_pre_ping=True)
    Base.metadata.create_all(target)
    source_inspector = inspect(source)

    with target.begin() as target_connection:
        if replace:
            for table_name in reversed(TABLE_ORDER):
                target_connection.execute(delete(Base.metadata.tables[table_name]))
        else:
            occupied = {
                name: target_connection.scalar(
                    select(func.count()).select_from(Base.metadata.tables[name])
                )
                for name in TABLE_ORDER
            }
            if any(occupied.values()):
                details = ", ".join(f"{name}={count}" for name, count in occupied.items() if count)
                raise RuntimeError(
                    f"移行先にデータがあります ({details})。"
                    "全置換する場合は --replace を指定してください。"
                )

        counts = {}
        with source.connect() as source_connection:
            for table_name in TABLE_ORDER:
                if not source_inspector.has_table(table_name):
                    counts[table_name] = 0
                    continue
                source_table = Base.metadata.tables[table_name]
                source_columns = {
                    column["name"] for column in source_inspector.get_columns(table_name)
                }
                selected_columns = [
                    column for column in source_table.columns if column.name in source_columns
                ]
                rows = source_connection.execute(
                    select(*selected_columns).select_from(source_table)
                ).mappings().all()
                if rows:
                    target_connection.execute(source_table.insert(), [dict(row) for row in rows])
                counts[table_name] = len(rows)

        # PostgreSQLの自動採番を移行済みIDの次へ進めます。
        for table_name in TABLE_ORDER:
            target_connection.execute(
                text(
                    "SELECT setval(pg_get_serial_sequence(:table_name, 'id'), "
                    "COALESCE((SELECT MAX(id) FROM " + table_name + "), 1), "
                    "EXISTS(SELECT 1 FROM " + table_name + "))"
                ),
                {"table_name": table_name},
            )
    source.dispose()
    target.dispose()
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=str(DEFAULT_SOURCE),
        help="移行元SQLiteファイル（例: local.db / kakeibo.db）",
    )
    parser.add_argument(
        "--target",
        default=os.environ.get("DATABASE_URL"),
        help="移行先PostgreSQL URL（省略時はDATABASE_URL）",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="移行先のEQUAデータを全削除して置き換える",
    )
    arguments = parser.parse_args()
    if not arguments.target:
        parser.error("--target またはDATABASE_URLが必要です")
    counts = migrate(arguments.source, arguments.target, arguments.replace)
    print("移行が完了しました。")
    for table_name in TABLE_ORDER:
        print(f"{table_name}: {counts[table_name]}件")


if __name__ == "__main__":
    main()
