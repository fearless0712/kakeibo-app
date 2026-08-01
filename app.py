"""CSVにデータを保存する、初心者向けの家計簿アプリ。"""

import csv
import sys
from datetime import datetime
from pathlib import Path


def get_data_directory():
    """実行方法に合わせて、ユーザーデータの保存フォルダを返します。"""
    if getattr(sys, "frozen", False):
        # Macアプリ版は、アプリ本体ではなくユーザー専用フォルダへ保存します。
        directory = Path.home() / "Library" / "Application Support" / "Kakeibo"
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    return Path(__file__).parent


DATA_FILE = get_data_directory() / "kakeibo.csv"
FIELDNAMES = ["id", "date", "category", "memo", "amount"]
CATEGORIES = ["食費", "日用品", "交通費", "娯楽", "住居費", "その他"]


def initialize_file():
    """CSVファイルがなければ、見出し行を作成します。"""
    if not DATA_FILE.exists():
        with DATA_FILE.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
            writer.writeheader()


def load_records():
    """CSVから全データを読み込み、リストで返します。"""
    initialize_file()
    with DATA_FILE.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def save_records(records):
    """受け取った全データをCSVに保存します。"""
    with DATA_FILE.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(records)


def input_date():
    """正しい日付が入力されるまで繰り返します。"""
    while True:
        value = input("日付 (YYYY-MM-DD、空欄なら今日): ").strip()
        if not value:
            return datetime.now().strftime("%Y-%m-%d")
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError:
            print("日付は 2026-08-01 のように入力してください。")


def input_amount():
    """1円以上の整数が入力されるまで繰り返します。"""
    while True:
        value = input("金額 (円): ").strip()
        try:
            amount = int(value)
            if amount > 0:
                return amount
        except ValueError:
            pass
        print("金額は1以上の整数で入力してください。")


def choose_category():
    """番号でカテゴリを選んでもらいます。"""
    print("カテゴリを選んでください。")
    for number, category in enumerate(CATEGORIES, start=1):
        print(f"  {number}. {category}")

    while True:
        value = input("番号: ").strip()
        if value.isdigit() and 1 <= int(value) <= len(CATEGORIES):
            return CATEGORIES[int(value) - 1]
        print(f"1〜{len(CATEGORIES)}の番号を入力してください。")


def add_record():
    """新しい支出を1件追加します。"""
    records = load_records()
    new_id = max((int(record["id"]) for record in records), default=0) + 1
    record = {
        "id": new_id,
        "date": input_date(),
        "category": choose_category(),
        "memo": input("メモ: ").strip(),
        "amount": input_amount(),
    }
    records.append(record)
    save_records(records)
    print("\n支出を保存しました。")


def print_records(records):
    """支出データを見やすく表示します。"""
    if not records:
        print("データがありません。")
        return

    print("\n ID | 日付       | カテゴリ | 金額      | メモ")
    print("-" * 60)
    for record in records:
        amount = f'{int(record["amount"]):,}円'
        print(
            f'{int(record["id"]):>3} | {record["date"]} | '
            f'{record["category"]:<6} | {amount:>9} | {record["memo"]}'
        )
    total = sum(int(record["amount"]) for record in records)
    print("-" * 60)
    print(f"合計: {total:,}円")


def show_all():
    """全データを日付順で表示します。"""
    records = sorted(load_records(), key=lambda record: record["date"], reverse=True)
    print_records(records)


def show_monthly_summary():
    """指定した月の支出とカテゴリ別合計を表示します。"""
    while True:
        month = input("集計する月 (YYYY-MM): ").strip()
        try:
            datetime.strptime(month, "%Y-%m")
            break
        except ValueError:
            print("2026-08 のように入力してください。")

    records = [record for record in load_records() if record["date"].startswith(month)]
    print_records(records)
    if not records:
        return

    totals = {}
    for record in records:
        category = record["category"]
        totals[category] = totals.get(category, 0) + int(record["amount"])

    print("\nカテゴリ別")
    for category, total in sorted(totals.items(), key=lambda item: item[1], reverse=True):
        print(f"  {category}: {total:,}円")


def delete_record():
    """IDを指定して支出を1件削除します。"""
    records = load_records()
    print_records(records)
    if not records:
        return

    value = input("\n削除するID (中止は空欄): ").strip()
    if not value:
        print("削除を中止しました。")
        return

    remaining = [record for record in records if record["id"] != value]
    if len(remaining) == len(records):
        print("そのIDは見つかりませんでした。")
        return

    save_records(remaining)
    print("削除しました。")


def main():
    """メニューを表示し、選ばれた機能を実行します。"""
    initialize_file()
    actions = {
        "1": add_record,
        "2": show_all,
        "3": show_monthly_summary,
        "4": delete_record,
    }

    while True:
        print("\n=== かんたん家計簿 ===")
        print("1. 支出を追加")
        print("2. 一覧を見る")
        print("3. 月別に集計")
        print("4. データを削除")
        print("0. 終了")
        choice = input("選択: ").strip()

        if choice == "0":
            print("おつかれさまでした！")
            break
        action = actions.get(choice)
        if action:
            action()
        else:
            print("0〜4の番号を選んでください。")


if __name__ == "__main__":
    main()
