"""Tkinterで作った、ウィンドウ版の家計簿アプリ。"""

import tkinter as tk
import json
import platform
from datetime import datetime, timedelta
from tkinter import messagebox, simpledialog, ttk

# app.pyにあるCSV操作とカテゴリ一覧を再利用します。
from app import CATEGORIES, get_data_directory, initialize_file, load_records, save_records


# 画面全体で使う色をここにまとめています。
COLORS = {
    "background": "#0B1120",
    "surface": "#111827",
    "surface_light": "#1F2937",
    "border": "#334155",
    "text": "#F8FAFC",
    "muted": "#94A3B8",
    "primary": "#3B82F6",
    "primary_hover": "#2563EB",
    "danger": "#EF4444",
    "danger_hover": "#DC2626",
    "success": "#22C55E",
}

CATEGORY_COLORS = {
    "食費": "#FB7185",
    "日用品": "#38BDF8",
    "交通費": "#A78BFA",
    "娯楽": "#FBBF24",
    "住居費": "#34D399",
    "その他": "#94A3B8",
}

BUDGET_FILE = get_data_directory() / "budgets.json"


class KakeiboApp:
    """家計簿ウィンドウの部品と動作をまとめたクラスです。"""

    def __init__(self, root):
        self.root = root
        self.root.title("かんたん家計簿")
        self.root.geometry("1280x900")
        self.root.minsize(1000, 760)
        self.root.configure(background=COLORS["background"])
        # コンボボックスを開いたときの一覧にもダーク配色を適用します。
        self.root.option_add("*TCombobox*Listbox.background", COLORS["surface_light"])
        self.root.option_add("*TCombobox*Listbox.foreground", COLORS["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", COLORS["primary"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", "white")

        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.category_var = tk.StringVar(value=CATEGORIES[0])
        self.memo_var = tk.StringVar()
        self.amount_var = tk.StringVar()
        self.month_var = tk.StringVar(value=datetime.now().strftime("%Y-%m"))
        self.total_var = tk.StringVar(value="合計: 0円")
        self.summary_var = tk.StringVar(value="カテゴリ別: データなし")
        self.status_var = tk.StringVar(value="準備完了")
        self.dashboard_month = datetime.now().strftime("%Y-%m")
        self.spending_var = tk.StringVar(value="0円")
        self.budget_var = tk.StringVar(value="0円")
        self.remaining_var = tk.StringVar(value="0円")
        self.top_category_var = tk.StringVar(value="データなし")
        self.month_change_var = tk.StringVar(value="— %")

        self.configure_style()
        self.create_widgets()
        initialize_file()
        self.refresh_table()

    def configure_style(self):
        """文字や表の見た目を整えます。"""
        system = platform.system()
        self.font = "SF Pro Display" if system == "Darwin" else "Segoe UI"
        self.style = ttk.Style()
        # clamは色や余白をOS間で揃えやすいテーマです。
        self.style.theme_use("clam")

        self.style.configure(".", font=(self.font, 11), background=COLORS["background"])
        self.style.configure("App.TFrame", background=COLORS["background"])
        self.style.configure("Card.TFrame", background=COLORS["surface"])
        self.style.configure(
            "TLabel", background=COLORS["background"], foreground=COLORS["text"]
        )
        self.style.configure(
            "Card.TLabel", background=COLORS["surface"], foreground=COLORS["text"]
        )
        self.style.configure(
            "Muted.TLabel", background=COLORS["background"], foreground=COLORS["muted"]
        )
        self.style.configure(
            "CardMuted.TLabel", background=COLORS["surface"], foreground=COLORS["muted"]
        )
        self.style.configure(
            "Title.TLabel",
            background=COLORS["background"],
            foreground=COLORS["text"],
            font=(self.font, 25, "bold"),
        )
        self.style.configure(
            "Total.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["success"],
            font=(self.font, 20, "bold"),
        )
        self.style.configure(
            "TEntry",
            fieldbackground=COLORS["surface_light"],
            foreground=COLORS["text"],
            insertcolor=COLORS["text"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
            padding=10,
        )
        self.style.map("TEntry", bordercolor=[("focus", COLORS["primary"])])
        self.style.configure(
            "TCombobox",
            fieldbackground=COLORS["surface_light"],
            background=COLORS["surface_light"],
            foreground=COLORS["text"],
            arrowcolor=COLORS["text"],
            bordercolor=COLORS["border"],
            padding=9,
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", COLORS["surface_light"])],
            foreground=[("readonly", COLORS["text"])],
            bordercolor=[("focus", COLORS["primary"])],
        )
        self.style.configure(
            "Primary.TButton",
            background=COLORS["primary"],
            foreground="white",
            borderwidth=0,
            font=(self.font, 12, "bold"),
            padding=(20, 12),
        )
        self.style.map(
            "Primary.TButton",
            background=[("active", COLORS["primary_hover"]), ("pressed", COLORS["primary_hover"])],
        )
        self.style.configure(
            "Secondary.TButton",
            background=COLORS["surface_light"],
            foreground=COLORS["text"],
            borderwidth=0,
            font=(self.font, 11, "bold"),
            padding=(16, 11),
        )
        self.style.map("Secondary.TButton", background=[("active", COLORS["border"])])
        self.style.configure(
            "Danger.TButton",
            background=COLORS["danger"],
            foreground="white",
            borderwidth=0,
            font=(self.font, 11, "bold"),
            padding=(16, 11),
        )
        self.style.map("Danger.TButton", background=[("active", COLORS["danger_hover"])])
        self.style.configure(
            "Treeview",
            background=COLORS["surface"],
            fieldbackground=COLORS["surface"],
            foreground=COLORS["text"],
            borderwidth=0,
            rowheight=38,
            font=(self.font, 11),
        )
        self.style.map(
            "Treeview",
            background=[("selected", COLORS["primary"])],
            foreground=[("selected", "white")],
        )
        self.style.configure(
            "Treeview.Heading",
            background=COLORS["surface_light"],
            foreground=COLORS["muted"],
            borderwidth=0,
            relief="flat",
            font=(self.font, 10, "bold"),
            padding=(8, 11),
        )
        self.style.map("Treeview.Heading", background=[("active", COLORS["border"])])
        self.style.configure(
            "Vertical.TScrollbar",
            background=COLORS["surface_light"],
            troughcolor=COLORS["surface"],
            borderwidth=0,
            arrowcolor=COLORS["muted"],
        )
        self.style.configure(
            "TNotebook",
            background=COLORS["background"],
            borderwidth=0,
            tabmargins=(0, 0, 0, 0),
        )
        self.style.configure(
            "TNotebook.Tab",
            background=COLORS["surface_light"],
            foreground=COLORS["muted"],
            borderwidth=0,
            font=(self.font, 11, "bold"),
            padding=(18, 11),
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", COLORS["primary"]), ("active", COLORS["border"])],
            foreground=[("selected", "white"), ("active", COLORS["text"])],
        )

    def create_widgets(self):
        """ラベル、入力欄、ボタン、一覧表を配置します。"""
        container = ttk.Frame(self.root, padding=24, style="App.TFrame")
        container.pack(fill="both", expand=True)

        header = ttk.Frame(container, style="App.TFrame")
        header.pack(fill="x", pady=(0, 18))
        ttk.Label(header, text="◈ かんたん家計簿", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text=f"{self.dashboard_month} の家計状況",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        self.create_dashboard(container)

        form = ttk.Frame(container, padding=18, style="Card.TFrame")
        form.pack(fill="x", pady=(14, 0))
        ttk.Label(
            form, text="＋  新しい支出", style="Card.TLabel", font=(self.font, 14, "bold")
        ).grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 14))

        ttk.Label(form, text="日付", style="CardMuted.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.date_var, width=12).grid(
            row=2, column=0, padx=(0, 12), sticky="ew"
        )

        ttk.Label(form, text="カテゴリ", style="CardMuted.TLabel").grid(row=1, column=1, sticky="w")
        ttk.Combobox(
            form,
            textvariable=self.category_var,
            values=CATEGORIES,
            state="readonly",
            width=10,
        ).grid(row=2, column=1, padx=(0, 12), sticky="ew")

        ttk.Label(form, text="金額（円）", style="CardMuted.TLabel").grid(row=1, column=2, sticky="w")
        amount_entry = ttk.Entry(form, textvariable=self.amount_var, width=12)
        amount_entry.grid(row=2, column=2, padx=(0, 12), sticky="ew")

        ttk.Label(form, text="メモ", style="CardMuted.TLabel").grid(row=1, column=3, sticky="w")
        memo_entry = ttk.Entry(form, textvariable=self.memo_var)
        memo_entry.grid(row=2, column=3, padx=(0, 12), sticky="ew")
        form.columnconfigure(3, weight=1)

        ttk.Button(
            form, text="＋ 追加する", command=self.add_record, style="Primary.TButton"
        ).grid(
            row=2, column=4, sticky="ew"
        )
        amount_entry.bind("<Return>", lambda _event: self.add_record())
        memo_entry.bind("<Return>", lambda _event: self.add_record())

        filter_frame = ttk.Frame(container, style="App.TFrame")
        filter_frame.pack(fill="x", pady=(18, 10))
        ttk.Label(filter_frame, text="▣  表示する月", style="Muted.TLabel").pack(side="left")
        ttk.Entry(filter_frame, textvariable=self.month_var, width=10).pack(
            side="left", padx=8
        )
        ttk.Button(
            filter_frame, text="月別表示", command=self.refresh_table, style="Secondary.TButton"
        ).pack(
            side="left"
        )
        ttk.Button(
            filter_frame, text="すべて表示", command=self.show_all, style="Secondary.TButton"
        ).pack(
            side="left", padx=8
        )
        ttk.Button(
            filter_frame,
            text="▥  グラフを表示",
            command=self.show_charts,
            style="Primary.TButton",
        ).pack(side="left")
        ttk.Button(
            filter_frame,
            text="×  選択した行を削除",
            command=self.delete_record,
            style="Danger.TButton",
        ).pack(
            side="right"
        )

        table_frame = ttk.Frame(container, padding=1, style="Card.TFrame")
        table_frame.pack(fill="both", expand=True)
        columns = ("id", "date", "category", "amount", "memo")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        headings = {
            "id": "ID",
            "date": "◷  日付",
            "category": "●  カテゴリ",
            "amount": "¥  金額",
            "memo": "≡  メモ",
        }
        for column, heading in headings.items():
            self.tree.heading(column, text=heading)
        self.tree.column("id", width=50, anchor="center", stretch=False)
        self.tree.column("date", width=110, anchor="center", stretch=False)
        self.tree.column("category", width=100, anchor="center", stretch=False)
        self.tree.column("amount", width=110, anchor="e", stretch=False)
        self.tree.column("memo", width=300)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        summary = ttk.Frame(container, padding=16, style="Card.TFrame")
        summary.pack(fill="x", pady=(12, 0))
        summary_left = ttk.Frame(summary, style="Card.TFrame")
        summary_left.pack(side="left", fill="x", expand=True)
        ttk.Label(summary_left, textvariable=self.summary_var, style="CardMuted.TLabel").pack(anchor="w")
        ttk.Label(summary_left, textvariable=self.status_var, style="CardMuted.TLabel").pack(
            anchor="w", pady=(5, 0)
        )
        ttk.Label(summary, textvariable=self.total_var, style="Total.TLabel").pack(
            side="right"
        )

    def create_dashboard(self, container):
        """ホーム画面に指標カードと2種類のグラフを作ります。"""
        metrics = ttk.Frame(container, style="App.TFrame")
        metrics.pack(fill="x", pady=(0, 14))
        for column in range(5):
            metrics.columnconfigure(column, weight=1, uniform="metric")

        self.create_metric_card(
            metrics, 0, "●  今月の支出", self.spending_var, COLORS["primary"]
        )
        budget_card = self.create_metric_card(
            metrics, 1, "◎  今月の予算", self.budget_var, "#A78BFA"
        )
        ttk.Button(
            budget_card,
            text="予算を設定",
            command=self.set_budget,
            style="Secondary.TButton",
        ).pack(anchor="w", pady=(8, 0))
        self.create_metric_card(
            metrics, 2, "◒  残り予算", self.remaining_var, COLORS["success"]
        )
        self.create_metric_card(
            metrics, 3, "◆  一番多いカテゴリ", self.top_category_var, "#FBBF24"
        )
        self.create_metric_card(
            metrics, 4, "↗  前月比", self.month_change_var, "#38BDF8"
        )

        charts = ttk.Frame(container, style="App.TFrame")
        charts.pack(fill="x")
        charts.columnconfigure(0, weight=1, uniform="chart")
        charts.columnconfigure(1, weight=1, uniform="chart")

        pie_card = ttk.Frame(charts, padding=14, style="Card.TFrame")
        pie_card.grid(row=0, column=0, padx=(0, 7), sticky="nsew")
        bar_card = ttk.Frame(charts, padding=14, style="Card.TFrame")
        bar_card.grid(row=0, column=1, padx=(7, 0), sticky="nsew")
        ttk.Label(
            pie_card,
            text="カテゴリ別支出",
            style="Card.TLabel",
            font=(self.font, 13, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            bar_card,
            text="月別支出の推移",
            style="Card.TLabel",
            font=(self.font, 13, "bold"),
        ).pack(anchor="w")
        self.dashboard_pie = tk.Canvas(
            pie_card,
            height=190,
            background=COLORS["surface"],
            highlightthickness=0,
        )
        self.dashboard_bar = tk.Canvas(
            bar_card,
            height=190,
            background=COLORS["surface"],
            highlightthickness=0,
        )
        self.dashboard_pie.pack(fill="x", expand=True)
        self.dashboard_bar.pack(fill="x", expand=True)
        self.dashboard_pie.bind("<Configure>", lambda _event: self.draw_dashboard_charts())
        self.dashboard_bar.bind("<Configure>", lambda _event: self.draw_dashboard_charts())

    def create_metric_card(self, parent, column, title, variable, accent):
        """ダッシュボードの指標カードを1枚作ります。"""
        card = ttk.Frame(parent, padding=14, style="Card.TFrame")
        card.grid(row=0, column=column, padx=(0 if column == 0 else 5, 5), sticky="nsew")
        ttk.Label(card, text=title, style="CardMuted.TLabel").pack(anchor="w")
        value = tk.Label(
            card,
            textvariable=variable,
            background=COLORS["surface"],
            foreground=accent,
            font=(self.font, 17, "bold"),
            anchor="w",
        )
        value.pack(fill="x", pady=(8, 0))
        return card

    def load_budgets(self):
        """月別予算をJSONファイルから読み込みます。"""
        if not BUDGET_FILE.exists():
            return {}
        try:
            with BUDGET_FILE.open("r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def save_budgets(self, budgets):
        """月別予算をJSONファイルへ保存します。"""
        with BUDGET_FILE.open("w", encoding="utf-8") as file:
            json.dump(budgets, file, ensure_ascii=False, indent=2)

    def set_budget(self):
        """今月の予算を入力する小さなダイアログを開きます。"""
        budgets = self.load_budgets()
        current = int(budgets.get(self.dashboard_month, 0))
        budget = simpledialog.askinteger(
            "今月の予算",
            f"{self.dashboard_month} の予算を円単位で入力してください。",
            initialvalue=current or None,
            minvalue=0,
            parent=self.root,
        )
        if budget is None:
            return
        budgets[self.dashboard_month] = budget
        self.save_budgets(budgets)
        self.refresh_dashboard()
        self.status_var.set("✓ 今月の予算を保存しました")

    def refresh_dashboard(self):
        """今月の指標とホーム画面のグラフを最新状態にします。"""
        records = load_records()
        current_month = self.dashboard_month
        first_day = datetime.strptime(f"{current_month}-01", "%Y-%m-%d")
        previous_month = (first_day - timedelta(days=1)).strftime("%Y-%m")
        month_totals = {}
        category_totals = {}

        for record in records:
            month = record["date"][:7]
            amount = int(record["amount"])
            month_totals[month] = month_totals.get(month, 0) + amount
            if month == current_month:
                category = record["category"]
                category_totals[category] = category_totals.get(category, 0) + amount

        spending = month_totals.get(current_month, 0)
        previous = month_totals.get(previous_month, 0)
        budget = int(self.load_budgets().get(current_month, 0))
        remaining = budget - spending
        top_category = max(category_totals, key=category_totals.get, default=None)

        self.spending_var.set(f"{spending:,}円")
        self.budget_var.set(f"{budget:,}円")
        self.remaining_var.set(f"{remaining:,}円")
        if top_category:
            self.top_category_var.set(
                f"{top_category}  {category_totals[top_category]:,}円"
            )
        else:
            self.top_category_var.set("データなし")

        if previous:
            change = (spending - previous) / previous * 100
            arrow = "▲" if change > 0 else "▼" if change < 0 else "→"
            self.month_change_var.set(f"{arrow} {change:+.1f}%")
        elif spending:
            self.month_change_var.set("— %（前月なし）")
        else:
            self.month_change_var.set("0.0%")

        self.dashboard_month_totals = month_totals
        self.dashboard_category_totals = category_totals
        self.root.after_idle(self.draw_dashboard_charts)

    def draw_dashboard_charts(self):
        """ホーム画面の円グラフと棒グラフを描き直します。"""
        if not hasattr(self, "dashboard_month_totals"):
            return
        self.draw_dashboard_pie(
            self.dashboard_pie, self.dashboard_category_totals
        )
        self.draw_dashboard_bar(
            self.dashboard_bar, self.dashboard_month_totals
        )

    def draw_dashboard_pie(self, canvas, totals):
        """ホーム画面用のコンパクトな円グラフを描きます。"""
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 100 or height < 100:
            return
        if not totals:
            self.draw_empty_chart(canvas, width, height, "今月の支出データがありません")
            return

        total = sum(totals.values())
        diameter = min(138, height - 24)
        x1, y1 = 16, (height - diameter) / 2
        x2, y2 = x1 + diameter, y1 + diameter
        start_angle = 90
        sorted_totals = sorted(totals.items(), key=lambda item: item[1], reverse=True)
        for category, amount in sorted_totals:
            extent = -(amount / total * 360)
            canvas.create_arc(
                x1,
                y1,
                x2,
                y2,
                start=start_angle,
                extent=extent,
                fill=CATEGORY_COLORS.get(category, COLORS["muted"]),
                outline=COLORS["surface"],
                width=2,
            )
            start_angle += extent

        inset = diameter * 0.3
        canvas.create_oval(
            x1 + inset,
            y1 + inset,
            x2 - inset,
            y2 - inset,
            fill=COLORS["surface"],
            outline="",
        )
        canvas.create_text(
            (x1 + x2) / 2,
            (y1 + y2) / 2,
            text=self.format_short_yen(total),
            fill=COLORS["text"],
            font=(self.font, 10, "bold"),
        )

        legend_start = 180
        available = max(150, width - legend_start)
        column_width = available / 2
        for index, (category, amount) in enumerate(sorted_totals):
            column, row = index // 3, index % 3
            x = legend_start + column * column_width
            y = 30 + row * 50
            color = CATEGORY_COLORS.get(category, COLORS["muted"])
            canvas.create_oval(x, y, x + 10, y + 10, fill=color, outline="")
            canvas.create_text(
                x + 18,
                y - 3,
                text=category,
                anchor="nw",
                fill=COLORS["text"],
                font=(self.font, 10, "bold"),
            )
            canvas.create_text(
                x + 18,
                y + 17,
                text=f"{amount:,}円  {amount / total * 100:.0f}%",
                anchor="nw",
                fill=COLORS["muted"],
                font=(self.font, 9),
            )

    def draw_dashboard_bar(self, canvas, totals):
        """ホーム画面用の直近6か月の棒グラフを描きます。"""
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 100 or height < 100:
            return
        months = sorted(totals)[-6:]
        if not months:
            self.draw_empty_chart(canvas, width, height, "支出データがありません")
            return

        left, right, top, bottom = 42, 14, 25, 34
        chart_width = width - left - right
        chart_height = height - top - bottom
        maximum = max(totals[month] for month in months)
        slot_width = chart_width / len(months)

        for step in range(3):
            y = top + chart_height * step / 2
            canvas.create_line(left, y, width - right, y, fill=COLORS["border"])
        for index, month in enumerate(months):
            amount = totals[month]
            x = left + slot_width * (index + 0.5)
            bar_height = chart_height * amount / maximum
            y = top + chart_height - bar_height
            canvas.create_rectangle(
                x - min(24, slot_width * 0.28),
                y,
                x + min(24, slot_width * 0.28),
                top + chart_height,
                fill=COLORS["primary"],
                outline="",
            )
            canvas.create_text(
                x,
                max(10, y - 9),
                text=self.format_short_yen(amount),
                fill=COLORS["text"],
                font=(self.font, 8, "bold"),
            )
            canvas.create_text(
                x,
                top + chart_height + 18,
                text=month[2:].replace("-", "/"),
                fill=COLORS["muted"],
                font=(self.font, 9),
            )

    def validate_date(self, value, format_string, example):
        """日付形式を確認し、間違っていればメッセージを表示します。"""
        try:
            datetime.strptime(value, format_string)
            return True
        except ValueError:
            messagebox.showerror("入力エラー", f"日付は {example} の形式で入力してください。")
            return False

    def add_record(self):
        """フォームの内容をCSVへ追加します。"""
        date = self.date_var.get().strip()
        amount_text = self.amount_var.get().replace(",", "").strip()
        if not self.validate_date(date, "%Y-%m-%d", "2026-08-01"):
            return
        try:
            amount = int(amount_text)
            if amount <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("入力エラー", "金額は1以上の整数で入力してください。")
            return

        records = load_records()
        new_id = max((int(record["id"]) for record in records), default=0) + 1
        records.append(
            {
                "id": new_id,
                "date": date,
                "category": self.category_var.get(),
                "memo": self.memo_var.get().strip(),
                "amount": amount,
            }
        )
        save_records(records)
        self.amount_var.set("")
        self.memo_var.set("")
        self.month_var.set(date[:7])
        self.refresh_table()
        self.status_var.set("✓ 支出を追加しました")

    def get_filtered_records(self):
        """入力された月に一致するデータを返します。"""
        month = self.month_var.get().strip()
        if not self.validate_date(month, "%Y-%m", "2026-08"):
            return None
        return [record for record in load_records() if record["date"].startswith(month)]

    def refresh_table(self, records=None):
        """一覧表と合計表示を最新状態にします。"""
        if records is None:
            records = self.get_filtered_records()
        if records is None:
            return

        for item in self.tree.get_children():
            self.tree.delete(item)

        records = sorted(records, key=lambda record: (record["date"], int(record["id"])), reverse=True)
        totals = {}
        for record in records:
            amount = int(record["amount"])
            self.tree.insert(
                "",
                "end",
                iid=record["id"],
                values=(
                    record["id"],
                    record["date"],
                    record["category"],
                    f"{amount:,}円",
                    record["memo"],
                ),
                tags=(record["category"],),
            )
            totals[record["category"]] = totals.get(record["category"], 0) + amount

        total = sum(totals.values())
        self.total_var.set(f"合計: {total:,}円")
        details = " / ".join(f"{name}: {value:,}円" for name, value in totals.items())
        self.summary_var.set(f"カテゴリ別: {details or 'データなし'}")
        self.status_var.set(f"{len(records)}件の支出を表示中")

        # カテゴリごとに文字色を変え、表を見分けやすくします。
        for category, color in CATEGORY_COLORS.items():
            self.tree.tag_configure(category, foreground=color)

        # 一覧だけでなく、ホームの指標とグラフも同時に更新します。
        self.refresh_dashboard()

    def show_all(self):
        """月に関係なく、すべてのデータを表示します。"""
        self.refresh_table(load_records())

    def show_charts(self):
        """棒グラフと円グラフを別ウィンドウで表示します。"""
        month = self.month_var.get().strip()
        if not self.validate_date(month, "%Y-%m", "2026-08"):
            return

        records = load_records()
        month_totals = {}
        category_totals = {}
        for record in records:
            record_month = record["date"][:7]
            amount = int(record["amount"])
            month_totals[record_month] = month_totals.get(record_month, 0) + amount
            if record_month == month:
                category = record["category"]
                category_totals[category] = category_totals.get(category, 0) + amount

        chart_window = tk.Toplevel(self.root)
        chart_window.title("支出グラフ")
        chart_window.geometry("900x620")
        chart_window.minsize(700, 500)
        chart_window.configure(background=COLORS["background"])

        header = ttk.Frame(chart_window, padding=(24, 20, 24, 10), style="App.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="▥ 支出レポート", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="支出の傾向をグラフで確認できます",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        notebook = ttk.Notebook(chart_window)
        notebook.pack(fill="both", expand=True, padx=24, pady=(6, 24))
        bar_tab = ttk.Frame(notebook, padding=16, style="Card.TFrame")
        pie_tab = ttk.Frame(notebook, padding=16, style="Card.TFrame")
        notebook.add(bar_tab, text="  月別支出（棒グラフ）  ")
        notebook.add(pie_tab, text=f"  {month} カテゴリ別（円グラフ）  ")

        bar_canvas = tk.Canvas(
            bar_tab, background=COLORS["surface"], highlightthickness=0
        )
        pie_canvas = tk.Canvas(
            pie_tab, background=COLORS["surface"], highlightthickness=0
        )
        bar_canvas.pack(fill="both", expand=True)
        pie_canvas.pack(fill="both", expand=True)

        # ウィンドウサイズが変わったときもグラフを描き直します。
        bar_canvas.bind(
            "<Configure>",
            lambda event: self.draw_bar_chart(event.widget, month_totals),
        )
        pie_canvas.bind(
            "<Configure>",
            lambda event: self.draw_pie_chart(event.widget, category_totals, month),
        )
        self.status_var.set("グラフ画面を開きました")

    def draw_bar_chart(self, canvas, totals):
        """月ごとの支出を棒グラフとして描画します。"""
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 100 or height < 100:
            return

        months = sorted(totals)[-12:]
        if not months:
            self.draw_empty_chart(canvas, width, height, "支出データがありません")
            return

        margin_left, margin_right = 76, 28
        margin_top, margin_bottom = 55, 62
        chart_width = width - margin_left - margin_right
        chart_height = height - margin_top - margin_bottom
        maximum = max(totals[month] for month in months)

        canvas.create_text(
            margin_left,
            22,
            text="月ごとの支出（直近12か月）",
            anchor="w",
            fill=COLORS["text"],
            font=(self.font, 15, "bold"),
        )

        # 横方向の補助線と金額目盛りを描きます。
        for step in range(5):
            ratio = step / 4
            y = margin_top + chart_height * ratio
            value = maximum * (1 - ratio)
            canvas.create_line(
                margin_left,
                y,
                width - margin_right,
                y,
                fill=COLORS["border"],
            )
            canvas.create_text(
                margin_left - 10,
                y,
                text=self.format_short_yen(value),
                anchor="e",
                fill=COLORS["muted"],
                font=(self.font, 9),
            )

        slot_width = chart_width / len(months)
        bar_width = min(52, slot_width * 0.62)
        for index, month in enumerate(months):
            amount = totals[month]
            x_center = margin_left + slot_width * (index + 0.5)
            bar_height = chart_height * amount / maximum
            y_top = margin_top + chart_height - bar_height
            canvas.create_rectangle(
                x_center - bar_width / 2,
                y_top,
                x_center + bar_width / 2,
                margin_top + chart_height,
                fill=COLORS["primary"],
                outline="",
            )
            canvas.create_text(
                x_center,
                y_top - 9,
                text=self.format_short_yen(amount),
                fill=COLORS["text"],
                font=(self.font, 9, "bold"),
            )
            canvas.create_text(
                x_center,
                margin_top + chart_height + 20,
                text=month[2:].replace("-", "/"),
                fill=COLORS["muted"],
                font=(self.font, 9),
            )

    def draw_pie_chart(self, canvas, totals, month):
        """指定月のカテゴリ別支出を円グラフとして描画します。"""
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 100 or height < 100:
            return
        if not totals:
            self.draw_empty_chart(canvas, width, height, f"{month} の支出データがありません")
            return

        total = sum(totals.values())
        diameter = min(height - 130, width * 0.52)
        diameter = max(diameter, 180)
        x1 = max(36, (width * 0.53 - diameter) / 2)
        y1 = (height - diameter) / 2 + 20
        x2, y2 = x1 + diameter, y1 + diameter

        canvas.create_text(
            28,
            22,
            text=f"{month} のカテゴリ別支出",
            anchor="w",
            fill=COLORS["text"],
            font=(self.font, 15, "bold"),
        )

        start_angle = 90
        sorted_totals = sorted(totals.items(), key=lambda item: item[1], reverse=True)
        for category, amount in sorted_totals:
            extent = -(amount / total * 360)
            canvas.create_arc(
                x1,
                y1,
                x2,
                y2,
                start=start_angle,
                extent=extent,
                fill=CATEGORY_COLORS.get(category, COLORS["muted"]),
                outline=COLORS["surface"],
                width=3,
            )
            start_angle += extent

        # 中央に穴を重ねてドーナツ型にし、合計を表示します。
        inset = diameter * 0.29
        canvas.create_oval(
            x1 + inset,
            y1 + inset,
            x2 - inset,
            y2 - inset,
            fill=COLORS["surface"],
            outline="",
        )
        canvas.create_text(
            (x1 + x2) / 2,
            (y1 + y2) / 2 - 11,
            text="合計",
            fill=COLORS["muted"],
            font=(self.font, 10),
        )
        canvas.create_text(
            (x1 + x2) / 2,
            (y1 + y2) / 2 + 13,
            text=f"{total:,}円",
            fill=COLORS["text"],
            font=(self.font, 15, "bold"),
        )

        legend_x = max(width * 0.60, x2 + 30)
        legend_y = max(76, height / 2 - len(sorted_totals) * 25)
        for index, (category, amount) in enumerate(sorted_totals):
            y = legend_y + index * 50
            color = CATEGORY_COLORS.get(category, COLORS["muted"])
            canvas.create_oval(legend_x, y, legend_x + 12, y + 12, fill=color, outline="")
            canvas.create_text(
                legend_x + 22,
                y + 1,
                text=category,
                anchor="nw",
                fill=COLORS["text"],
                font=(self.font, 11, "bold"),
            )
            percentage = amount / total * 100
            canvas.create_text(
                legend_x + 22,
                y + 22,
                text=f"{amount:,}円  ({percentage:.1f}%)",
                anchor="nw",
                fill=COLORS["muted"],
                font=(self.font, 10),
            )

    def draw_empty_chart(self, canvas, width, height, message):
        """グラフに表示するデータがない場合の案内です。"""
        canvas.create_text(
            width / 2,
            height / 2,
            text=f"▥\n\n{message}",
            justify="center",
            fill=COLORS["muted"],
            font=(self.font, 13),
        )

    @staticmethod
    def format_short_yen(amount):
        """グラフ用に金額を短い表記へ変換します。"""
        if amount >= 10000:
            return f"{amount / 10000:.1f}万"
        return f"{int(amount):,}円"

    def delete_record(self):
        """一覧で選択された支出を削除します。"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("削除", "削除する行をクリックして選んでください。")
            return
        if not messagebox.askyesno("削除の確認", "選択した支出を削除しますか？"):
            return

        selected_ids = set(selected)
        records = [record for record in load_records() if record["id"] not in selected_ids]
        save_records(records)
        self.refresh_table()
        self.status_var.set("✓ 選択した支出を削除しました")


def main():
    """ウィンドウを作成し、アプリを開始します。"""
    root = tk.Tk()
    KakeiboApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
