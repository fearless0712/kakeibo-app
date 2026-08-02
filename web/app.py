"""EQUA資産管理アプリのWeb/PWA版。"""

import io
import os
import secrets
import sys
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, send_from_directory, session, url_for
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user


# ルートにある共有データ層をWeb版から読み込めるようにします。
PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app import CATEGORIES  # noqa: E402
from database import (  # noqa: E402
    add_expense,
    delete_expense,
    delete_import_history,
    create_user,
    get_budgets,
    get_account_balances,
    get_asset_dashboard,
    get_annual_reports,
    get_expenses,
    get_financial_summary,
    get_import_history,
    get_import_record,
    get_lifetime_statistics,
    get_category_ranking,
    get_user_by_id,
    get_user_by_username,
    get_data_directory,
    import_bank_transactions,
    initialize_database,
    reset_user_data,
    search_transactions,
    set_month_budget,
)
from web.parsers import PARSERS, detect_parser  # noqa: E402
from utils.datetime import format_datetime  # noqa: E402


app = Flask(__name__)
VERSION_FILE = PROJECT_DIR / "VERSION"
APP_VERSION = (
    VERSION_FILE.read_text(encoding="utf-8").strip().removeprefix("v")
    if VERSION_FILE.exists()
    else "2.0.0"
)
PENDING_IMPORT_DIR = get_data_directory() / "pending_imports"
app.config["SECRET_KEY"] = os.environ.get(
    "KAKEIBO_SECRET_KEY", "development-only-change-this-key"
)
app.config.update(
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = None
login_manager.session_protection = "strong"
app.jinja_env.filters["datetime_jst"] = format_datetime


@app.context_processor
def inject_version():
    """全画面でVersion 2表示を利用できるようにします。"""
    return {"app_version": APP_VERSION}


class User(UserMixin):
    """Flask-Loginが扱うログインユーザー。"""

    def __init__(self, record):
        self.id = str(record["id"])
        self.username = record["username"]
        self.password_hash = record["password_hash"]


@login_manager.user_loader
def load_user(user_id):
    """セッション内のIDからユーザーを復元します。"""
    try:
        record = get_user_by_id(int(user_id))
    except (TypeError, ValueError):
        return None
    return User(record) if record else None


def valid_date(value, format_string):
    """文字列が指定した日付形式か確認します。"""
    try:
        datetime.strptime(value, format_string)
        return True
    except ValueError:
        return False


def log_import_result(source, parser_name, result, current_balance=None):
    """CSVインポート結果を一定の形式でログへ出力します。"""
    app.logger.info(
        "Import source: %s\nDetected parser: %s\nImported: %d\nSkipped: %d\nIncome: %d\nExpense: %d\nCurrent balance: %s",
        source,
        parser_name,
        result["imported"],
        result["skipped"],
        result["income"],
        result["expense"],
        current_balance if current_balance is not None else "N/A",
    )


def parser_error_summary(errors):
    """Parserエラーをユーザー向けの原因へ変換します。"""
    if not errors:
        return "取引データがありません"
    details = " / ".join(str(item.get("message", "")) for item in errors[:3])
    if any("ヘッダー" in item.get("message", "") for item in errors):
        reason = "必要な列が見つかりません"
    elif any("準備中" in item.get("message", "") for item in errors):
        reason = "対応していないCSV形式です"
    else:
        reason = "取引データがありません"
    return f"{reason}\n詳細：{details}" if details else reason


def clear_pending_import(token):
    """手動判定用の一時CSVとセッション情報を削除します。"""
    if not token:
        return
    (PENDING_IMPORT_DIR / f"{token}.csv").unlink(missing_ok=True)
    session.pop("pending_import_token", None)
    session.pop("pending_import_filename", None)


def build_dashboard(selected_month, user_id, query="", filter_kind="", category="", bank=""):
    """画面表示に必要な一覧・集計・グラフデータを作ります。"""
    all_expenses = get_expenses(user_id=user_id)
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
    budget = int(get_budgets(user_id=user_id).get(selected_month, 0))
    first_day = datetime.strptime(f"{selected_month}-01", "%Y-%m-%d")
    previous_month = (first_day - timedelta(days=1)).strftime("%Y-%m")
    previous_spending = monthly_totals.get(previous_month, 0)
    if previous_spending:
        month_change = (spending - previous_spending) / previous_spending * 100
    else:
        month_change = None

    top_category = max(category_totals, key=category_totals.get, default=None)
    recent_months = sorted(monthly_totals)[-12:]
    dashboard = {
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
    dashboard.update(get_financial_summary(user_id, selected_month))
    dashboard["account_balances"] = get_account_balances(user_id)
    dashboard.update(get_asset_dashboard(user_id, selected_month))
    dashboard.update(get_lifetime_statistics(user_id))
    dashboard["category_ranking"] = get_category_ranking(user_id)
    dashboard["annual_reports"] = get_annual_reports(user_id)
    dashboard["transactions"] = search_transactions(
        user_id, query=query, filter_kind=filter_kind, category=category, bank=bank
    )
    dashboard["bank_options"] = sorted(
        {item["institution"] for item in dashboard["account_balances"]}
    )
    return dashboard


@app.get("/")
@login_required
def index():
    """ダッシュボードと支出一覧を表示します。"""
    selected_month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    if not valid_date(selected_month, "%Y-%m"):
        selected_month = datetime.now().strftime("%Y-%m")
    query = request.args.get("q", "").strip()
    filter_kind = request.args.get("filter", "").strip()
    category_filter = request.args.get("category", "").strip()
    bank_filter = request.args.get("bank", "").strip()
    dashboard = build_dashboard(
        selected_month,
        int(current_user.id),
        query=query,
        filter_kind=filter_kind,
        category=category_filter,
        bank=bank_filter,
    )
    return render_template(
        "index.html",
        selected_month=selected_month,
        today=datetime.now().strftime("%Y-%m-%d"),
        categories=CATEGORIES,
        status=request.args.get("status", ""),
        version=APP_VERSION,
        search_query=query,
        filter_kind=filter_kind,
        category_filter=category_filter,
        bank_filter=bank_filter,
        **dashboard,
    )


@app.post("/expenses")
@login_required
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
    add_expense(date, category, memo, amount, user_id=int(current_user.id))
    return redirect(url_for("index", month=month, status="added"))


@app.post("/expenses/<int:expense_id>/delete")
@login_required
def remove_expense(expense_id):
    """指定された支出を削除します。"""
    month = request.form.get("month", datetime.now().strftime("%Y-%m"))
    delete_expense(expense_id, user_id=int(current_user.id))
    return redirect(url_for("index", month=month, status="deleted"))


@app.route("/import-csv", methods=["GET", "POST"])
@login_required
def import_csv():
    """金融機関を自動判定し、共通形式で取引を取り込みます。"""
    parser_options = [
        {"key": key, "name": parser.display_name} for key, parser in PARSERS.items()
    ]
    if request.method == "GET":
        error = (
            "CSVファイルは2MB以内にしてください。"
            if request.args.get("error") == "file_too_large"
            else ""
        )
        return render_template("import_csv.html", parsers=parser_options, error=error)

    selected_key = request.form.get("parser", "auto")
    pending_token = request.form.get("pending_token", "")
    data = None
    filename = ""
    if pending_token and pending_token == session.get("pending_import_token"):
        pending_path = PENDING_IMPORT_DIR / f"{pending_token}.csv"
        if pending_path.exists():
            data = pending_path.read_bytes()
            filename = session.get("pending_import_filename", "CSVファイル")
    else:
        upload = request.files.get("csv_file")
        if upload and upload.filename:
            data = upload.read()
            filename = upload.filename

    if not data:
        return render_template(
            "import_csv.html",
            parsers=parser_options,
            error="CSVファイルを選択してください。",
        )

    parser_class = detect_parser(data) if selected_key == "auto" else PARSERS.get(selected_key)
    if parser_class is None:
        token = secrets.token_urlsafe(24)
        PENDING_IMPORT_DIR.mkdir(parents=True, exist_ok=True)
        (PENDING_IMPORT_DIR / f"{token}.csv").write_bytes(data)
        old_token = session.get("pending_import_token")
        if old_token and old_token != token:
            (PENDING_IMPORT_DIR / f"{old_token}.csv").unlink(missing_ok=True)
        session["pending_import_token"] = token
        session["pending_import_filename"] = filename
        return render_template(
            "import_csv.html",
            parsers=parser_options,
            needs_selection=True,
            pending_token=token,
            filename=filename,
            error="金融機関を自動判定できませんでした。銀行・カード会社を選択してください。",
        )

    parser = parser_class()
    try:
        transactions = parser.parse(io.BytesIO(data))
    except (TypeError, ValueError) as error:
        result = {"imported": 0, "skipped": 0, "income": 0, "expense": 0}
        log_import_result(parser.import_name, parser.__class__.__name__, result)
        flash(
            f"❌ CSVの解析に失敗しました\n使用Parser：{parser.__class__.__name__}\n詳細：{error}",
            "error",
        )
        clear_pending_import(pending_token)
        return redirect(url_for("index"))

    if not transactions:
        result = {"imported": 0, "skipped": 0, "income": 0, "expense": 0}
        log_import_result(parser.import_name, parser.__class__.__name__, result)
        flash(
            f"❌ {parser_error_summary(parser.errors)}\n使用Parser：{parser.__class__.__name__}",
            "error",
        )
        clear_pending_import(pending_token)
        return redirect(url_for("index"))

    # current_user.idを明示的に渡し、別ユーザーのデータへ混ざるのを防ぎます。
    user_id = int(current_user.id)
    result = import_bank_transactions(
        transactions,
        user_id=user_id,
        source=parser.source_key,
        csv_type=parser.import_name,
        bank=parser.display_name,
        account_key=f"{parser.source_key}:default",
        filename=filename,
        parser_key=parser.source_key,
        raw_csv=data,
    )
    result["errors"] += len(parser.errors)

    # 金融機関を手動選択した場合に保存した一時CSVを確実に削除します。
    clear_pending_import(pending_token)

    # 取り込んだ最新取引の月を表示し、結果件数をダッシュボードへ渡します。
    selected_month = (
        max(transaction["date"] for transaction in transactions)[:7]
        if transactions
        else datetime.now().strftime("%Y-%m")
    )
    parser_name = parser.__class__.__name__
    balance = get_financial_summary(user_id, selected_month)["current_balance"]
    log_import_result(parser.import_name, parser_name, result, balance)
    balance_message = (
        f"残高更新：{balance:,}円" if balance is not None else "残高更新：残高情報なし"
    )
    flash(
        "\n".join(
            (
                f"✅ {parser.import_name}を読み込みました。",
                f"使用Parser：{parser_name}",
                f"新規登録：{result['imported']}件",
                f"重複スキップ：{result['skipped']}件",
                f"収入：{result['income']}件 / 支出：{result['expense']}件",
                balance_message,
                f"エラー：{result['errors']}件",
            )
        ),
        "success",
    )
    return redirect(url_for("index", month=selected_month))


@app.get("/admin")
@login_required
def admin():
    """インポート履歴とデータ管理画面を表示します。"""
    history = get_import_history(int(current_user.id))
    return render_template("admin.html", history=history)


@app.post("/admin/import-history/<int:history_id>/delete")
@login_required
def remove_import_history(history_id):
    """所有者のCSV取込を取引とともに取り消します。"""
    result = delete_import_history(history_id, int(current_user.id))
    if result:
        flash(
            f"✅ CSVインポートを取り消しました。削除取引：{result['transactions']}件",
            "success",
        )
    else:
        flash("❌ 指定された履歴が見つかりません。", "error")
    return redirect(url_for("admin"))


@app.post("/admin/import-history/<int:history_id>/reimport")
@login_required
def reimport_history(history_id):
    """保存済みCSVを現在のParserと重複判定で再取込します。"""
    user_id = int(current_user.id)
    record = get_import_record(history_id, user_id)
    if not record or not record.get("raw_csv"):
        flash("❌ 元CSVが保存されていないため再インポートできません。", "error")
        return redirect(url_for("admin"))
    parser_class = PARSERS.get(record.get("parser_key")) or detect_parser(record["raw_csv"])
    if parser_class is None:
        flash("❌ CSV Parserを判定できません。", "error")
        return redirect(url_for("admin"))
    parser = parser_class()
    transactions = parser.parse(io.BytesIO(record["raw_csv"]))
    if not transactions:
        flash(f"❌ {parser_error_summary(parser.errors)}", "error")
        return redirect(url_for("admin"))
    result = import_bank_transactions(
        transactions,
        user_id=user_id,
        source=parser.source_key,
        csv_type=parser.import_name,
        bank=parser.display_name,
        account_key=f"{parser.source_key}:default",
        filename=record.get("filename"),
        parser_key=parser.source_key,
        raw_csv=record["raw_csv"],
    )
    flash(
        f"✅ 再インポート完了：追加 {result['imported']}件 / 重複 {result['skipped']}件",
        "success",
    )
    return redirect(url_for("admin"))


@app.post("/admin/reset")
@login_required
def reset_all_data():
    """ログインユーザーの取引・履歴・重複判定をリセットします。"""
    if request.form.get("confirmation") != "RESET":
        flash("❌ 確認文字が一致しないため、データを削除しませんでした。", "error")
        return redirect(url_for("admin"))
    deleted = reset_user_data(int(current_user.id))
    flash(
        "\n".join(
            (
                "✅ 全データをリセットしました。",
                f"支出：{deleted['expenses']}件",
                f"取引・重複判定：{deleted['transactions']}件",
                f"インポート履歴：{deleted['history']}件",
                "ユーザーアカウントと予算は削除されていません。",
            )
        ),
        "success",
    )
    return redirect(url_for("admin"))


@app.errorhandler(413)
def file_too_large(_error):
    """大きすぎるCSVを分かりやすいメッセージへ変換します。"""
    return redirect(url_for("import_csv", error="file_too_large"))


@app.post("/budget")
@login_required
def update_budget():
    """選択月の予算を保存します。"""
    month = request.form.get("month", "").strip()
    try:
        amount = int(request.form.get("budget", "").replace(",", ""))
        if amount < 0 or not valid_date(month, "%Y-%m"):
            raise ValueError
    except ValueError:
        return redirect(url_for("index", month=month, status="invalid_budget"))
    set_month_budget(month, amount, user_id=int(current_user.id))
    return redirect(url_for("index", month=month, status="budget_saved"))


@app.route("/register", methods=["GET", "POST"])
def register():
    """新しいユーザーを登録します。"""
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    error = ""
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password_confirmation = request.form.get("password_confirmation", "")
        if not 3 <= len(username) <= 30:
            error = "ユーザー名は3〜30文字で入力してください。"
        elif len(password) < 8:
            error = "パスワードは8文字以上で入力してください。"
        elif len(password.encode("utf-8")) > 72:
            error = "パスワードは72バイト以内で入力してください。"
        elif password != password_confirmation:
            error = "確認用パスワードが一致しません。"
        elif get_user_by_username(username):
            error = "このユーザー名はすでに使用されています。"
        else:
            password_hash = bcrypt.generate_password_hash(password).decode("utf-8")
            record = create_user(username, password_hash)
            if record:
                login_user(User(record))
                return redirect(url_for("index", status="registered"))
            error = "ユーザー登録に失敗しました。"
    return render_template(
        "auth.html", mode="register", error=error, username=username
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    """ユーザー名とパスワードでログインします。"""
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    error = ""
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        record = get_user_by_username(username)
        password_matches = False
        if record:
            try:
                password_matches = bcrypt.check_password_hash(
                    record["password_hash"], password
                )
            except ValueError:
                password_matches = False
        if password_matches:
            login_user(User(record), remember=request.form.get("remember") == "on")
            next_url = request.args.get("next", "")
            if next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("index"))
        error = "ユーザー名またはパスワードが正しくありません。"
    return render_template("auth.html", mode="login", error=error, username=username)


@app.post("/logout")
@login_required
def logout():
    """ログアウトしてログイン画面へ戻ります。"""
    logout_user()
    return redirect(url_for("login"))


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
