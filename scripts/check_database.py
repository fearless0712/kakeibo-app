#!/usr/bin/env python3
"""現在の接続先DBと主要テーブル件数を安全に表示する。"""

import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from database import get_database_status, initialize_database  # noqa: E402


initialize_database()
status = get_database_status()
print(f"DATABASE_URL present: {str(status['database_url_present']).lower()}")
print(f"Backend: {status['backend']}")
print(f"URL: {status['safe_url']}")
print(f"Host: {status['host']}")
print(f"Database: {status['database']}")
for table_name, count in status["counts"].items():
    print(f"{table_name}: {count}")
