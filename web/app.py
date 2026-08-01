"""Flaskで動く、かんたん家計簿のWeb/PWA版。"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, redirect, render_template, request, send_from_directory, url_for


# ルートにある共有データ層をWeb版から読み込めるようにします。
PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app import CATEGORIES  # noqa: E402
from database import (  # noqa: E402
    add_expense,
    delete_expense,
    get_budgets,
    get_expenses,
    initialize_database,
    set_month_budget,
)


app = Flask(__name__)


def valid_date(value, format_string):
    """文字列が指定した日付形式か確認します。"""
    try:
        datetime.strptime(value, format_string)
        return True
    except ValueError:
        return False


def build_dashboard(selected_month):
    """画面表示に必要な一覧・集計・グラフデータを作ります。"""
    all_expenses = get_expenses()
    expenses = [item for item in all_expenses if item["date"].startswith(selected_month)]
    category_totals = {}
    monthly_totals = {}
    for expense in all_expenses:
        month = expense["date"][:7]
        monthly_totals[month] = monthly_totals.get(month, 0) + expense["amount"]
        if month == selected_month:
            category = expense["category"]
            category_totals[category] = category_totals.get(category, 0) + expense["amount"]

    spending = sum(category_totals.values())
    budget = int(get_budgets().get(selected_month, 0))
    first_day = datetime.strptime(f"{selected_month}-01", "%Y-%m-%d")
    previous_month = (first_day - timedelta(days=1)).strftime("%Y-%m")
    previous_spending = monthly_totals.get(previous_month, 0)
    if previous_spending:
        month_change = (spending - previous_spending) / previous_spending * 100
    else:
        month_change = None

    top_category = max(category_totals, key=category_totals.get, default=None)
    recent_months = sorted(monthly_totals)[-12:]
    return {
        "expenses": expenses,
        "spending": spending,
        "budget": budget,
        "remaining": budget - spending,
        "top_category": top_category,
        "top_category_amount": category_totals.get(top_category, 0),
        "month_change": month_change,
        "category_chart": {
            "labels": list(category_totals),
            "values": list(category_totals.values()),
        },
        "monthly_chart": {
            "labels": recent_months,
            "values": [monthly_totals[month] for month in recent_months],
        },
    }


@app.get("/")
def index():
    """ダッシュボードと支出一覧を表示します。"""
    selected_month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    if not valid_date(selected_month, "%Y-%m"):
        selected_month = datetime.now().strftime("%Y-%m")
    dashboard = build_dashboard(selected_month)
    return render_template(
        "index.html",
        selected_month=selected_month,
        today=datetime.now().strftime("%Y-%m-%d"),
        categories=CATEGORIES,
        status=request.args.get("status", ""),
        **dashboard,
    )


@app.post("/expenses")
def create_expense():
    """入力された支出をSQLiteへ追加します。"""
    date = request.form.get("date", "").strip()
    category = request.form.get("category", "").strip()
    memo = request.form.get("memo", "").strip()
    amount_text = request.form.get("amount", "").replace(",", "").strip()
    month = date[:7] if len(date) >= 7 else datetime.now().strftime("%Y-%m")
    try:
        amount = int(amount_text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        return redirect(url_for("index", month=month, status="invalid_amount"))
    if not valid_date(date, "%Y-%m-%d") or category not in CATEGORIES:
        return redirect(url_for("index", month=month, status="invalid_input"))
    add_expense(date, category, memo, amount)
    return redirect(url_for("index", month=month, status="added"))


@app.post("/expenses/<int:expense_id>/delete")
def remove_expense(expense_id):
    """指定された支出を削除します。"""
    month = request.form.get("month", datetime.now().strftime("%Y-%m"))
    delete_expense(expense_id)
    return redirect(url_for("index", month=month, status="deleted"))


@app.post("/budget")
def update_budget():
    """選択月の予算を保存します。"""
    month = request.form.get("month", "").strip()
    try:
        amount = int(request.form.get("budget", "").replace(",", ""))
        if amount < 0 or not valid_date(month, "%Y-%m"):
            raise ValueError
    except ValueError:
        return redirect(url_for("index", month=month, status="invalid_budget"))
    set_month_budget(month, amount)
    return redirect(url_for("index", month=month, status="budget_saved"))


@app.get("/service-worker.js")
def service_worker():
    """ルートスコープでService Workerを配信します。"""
    response = send_from_directory(app.static_folder, "service-worker.js")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


if __name__ == "__main__":
    initialize_database()
    app.run(host="0.0.0.0", port=5000, debug=False)
