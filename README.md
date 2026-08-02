<div align="center">
  <img src="assets/app_icon.png" alt="EQUA app icon" width="128">

  # EQUA

  **CSVから資産・収支を一元管理する、ダークテーマの資産管理アプリ**

  [![Version](https://img.shields.io/badge/version-v2.0.0-38BDF8)](CHANGELOG.md)
  [![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
  [![Flask](https://img.shields.io/badge/Flask-3.x-111827?logo=flask)](https://flask.palletsprojects.com/)
  [![Platform](https://img.shields.io/badge/Web%20%7C%20PWA%20%7C%20Desktop-macOS%20%7C%20Windows-111827)](#セットアップ方法)
</div>

## EQUAとは

EQUAは、銀行CSVと手入力の取引を共通の資産台帳へまとめ、残高・収入・支出・資産推移を可視化する個人向け資産管理アプリです。

Flask製のWeb/PWA版を中心に、既存のTkinterデスクトップ版とターミナル版もSQLAlchemyデータ層を共有します。ローカルではSQLite、`DATABASE_URL`が設定された本番環境ではPostgreSQLを自動的に使用します。

## 特徴

- 銀行CSVを共通の`Transaction`資産台帳へ統合
- SQLAlchemy経由でSQLiteとPostgreSQLを自動切替
- DBには日時をUTCで保存し、画面では共通フィルターにより日本時間（JST）で表示
- `income`・`expense`に基づく一貫した収支集計
- 複数ユーザー・複数口座のデータ分離
- PCとスマートフォンに対応したダークテーマUI
- ホーム画面へ追加できるPWA
- 既存DBを削除しない自動マイグレーション
- 同一取引の重複スキップとCSV単位の取込取消
- Render・Railwayへのデプロイ設定

## 主な機能

### 資産ダッシュボード

- 現在残高、今月収入、今月支出、今月収支
- 前月残高、翌月繰越、予算、残り予算、前月比
- 総収入、総支出、累計収支、現在資産、総取引件数
- 平均月収・平均月支出、過去最高・最低残高
- 銀行・口座名・現在残高を表示する複数口座カード
- 現金、投資、合計資産のカード表示

### 分析・レポート

- Chart.jsによる全期間の月別資産推移
- 収入・支出・収支を比較する月別棒グラフ
- カテゴリー別支出円グラフと支出ランキング
- 年間収入、支出、貯蓄額、貯蓄率、年間収支、前年比

### 取引管理

- 支出の手入力・一覧・削除
- 日付、店舗名・メモ、カテゴリー、金額、銀行の部分一致検索
- 収入、支出、振込、カード、現金、カテゴリー、銀行フィルター
- 摘要から給与、Amazon、楽天市場、光熱費、交通、医療、投資などを自動分類

### CSVインポート

- ファイル選択とドラッグ＆ドロップ
- 列名・内容によるParser自動判定
- ユーザー別の重複判定と追加インポート
- 取込・重複・収入・支出・エラー件数のFlash表示とログ出力
- 銀行、CSV種類、件数、日時を確認できるインポート履歴
- 保存済みCSVの再インポート
- Version 2以降の履歴を対象としたCSV単位の取込取消と残高・集計の再計算

### 認証・PWA

- Flask-Loginによるログイン制御
- Flask-Bcryptによるパスワードハッシュ化
- ユーザーごとの取引・予算・口座・履歴分離
- Service Worker、Web App Manifest、オフライン画面

## スクリーンショット

スクリーンショットは`docs/screenshots/`へ追加します。

| ダッシュボード | CSVインポート | 管理画面 |
|:--:|:--:|:--:|
| `docs/screenshots/dashboard.png` | `docs/screenshots/csv-import.png` | `docs/screenshots/admin.png` |

<!-- 画像追加後、上のプレースホルダー行を次の形式へ置き換えてください。
| ![Dashboard](docs/screenshots/dashboard.png) | ![CSV import](docs/screenshots/csv-import.png) | ![Admin](docs/screenshots/admin.png) |
-->

## 技術スタック

| 技術 | 用途 |
|---|---|
| Python 3.10+ | アプリケーション、CSV解析、集計 |
| Flask / Jinja | Webルーティング、HTML生成 |
| Flask-Login | セッション認証とアクセス制御 |
| Flask-Bcrypt | パスワードのハッシュ化 |
| SQLAlchemy 2 | SQLite / PostgreSQL共通のORM・スキーマ管理 |
| SQLite | ローカル開発用の`local.db` |
| PostgreSQL / psycopg | Render・Railwayなどの本番データベース |
| HTML / CSS / JavaScript | レスポンシブなダークテーマUI |
| Bootstrap 5 | 認証画面などのUI基盤 |
| Chart.js | 資産・収支グラフ |
| PWA / Service Worker | ホーム画面追加とアプリシェルキャッシュ |
| Tkinter / ttk | デスクトップ版GUI |
| Gunicorn | 公開環境のWSGIサーバー |
| PyInstaller / Pillow | macOSアプリのビルドとアイコン変換 |

## セットアップ方法

### 必要環境

- Python 3.10以降
- Git
- デスクトップ版を使う場合はTkinter

### リポジトリを取得

```bash
git clone https://github.com/fearless0712/kakeibo-app.git
cd kakeibo-app
```

### Web / PWA版

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-web.txt
python3 web/app.py
```

Windows PowerShellでは仮想環境を次のように有効化します。

```powershell
.venv\Scripts\Activate.ps1
python web/app.py
```

ブラウザで<http://127.0.0.1:5000/register>を開き、最初のユーザーを登録してください。

`DATABASE_URL`がない場合はプロジェクト直下の`local.db`を使用します。PostgreSQLへ接続する場合は次のように設定します。

```bash
export DATABASE_URL="postgresql://user:password@host:5432/equa"
python3 web/app.py
```

### 公開環境向けGunicorn

```bash
python3 -m pip install -r requirements.txt
export KAKEIBO_SECRET_KEY="十分に長いランダム値"
gunicorn --workers 1 --threads 4 --bind 0.0.0.0:8000 web.app:app
```

SQLiteの保存先は`EQUA_DATA_DIR`で変更できます。PostgreSQL使用時は`DATABASE_URL`が優先されます。

```bash
export EQUA_DATA_DIR=/path/to/persistent/data
```

> `DATABASE_URL`を設定すると複数環境から1つのPostgreSQLデータベースを共有できます。

### Render

1. GitHubリポジトリをRenderへ接続します。
2. Blueprintとして`render.yaml`を読み込みます。
3. Web Serviceが既存の`kakeibo-db` PostgreSQLへ接続されることを確認します。
4. `DATABASE_URL`は`kakeibo-db`の内部`connectionString`から自動設定されます。
5. `KAKEIBO_SECRET_KEY`は設定ファイルに従って自動生成されます。

Render Dashboardで手動構成する場合は、Render PostgresのInternal Database URLをWeb Serviceの`DATABASE_URL`へ設定して再デプロイします。

### Railway

1. GitHubリポジトリをRailwayへ接続します。
2. PostgreSQL Serviceを追加します。
3. Railwayが提供する`DATABASE_URL`と`KAKEIBO_SECRET_KEY=<ランダム値>`をWeb Serviceへ設定します。
4. `railway.json`の起動設定を使用してデプロイします。

### SQLiteからPostgreSQLへ移行

ユーザー、口座、取引、CSVインポート履歴、支出ミラー、予算の全テーブルを移行します。

```bash
export DATABASE_URL="Render PostgresのExternal Database URL"
python3 scripts/migrate_sqlite_to_postgres.py --source kakeibo.db
```

`local.db`から移行する場合は`--source local.db`を指定します。移行先にデータがある場合は停止します。移行先を全置換する場合のみ`--replace`を付けてください。

### デスクトップ版

```bash
python3 gui_app.py
```

ターミナル版は次のコマンドで起動できます。

```bash
python3 app.py
```

### macOSアプリをビルド

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-build.txt
./scripts/build_macos.sh
```

出力先は`dist/かんたん家計簿.app`です。配布版のデータは`~/Library/Application Support/Kakeibo/`へ保存されます。

### テスト

```bash
python3 -m unittest discover -s tests -v
```

実際のPostgreSQLで新規登録・ログイン・Sony銀行CSV取込まで確認する場合は、検証用データベースのURLを指定します。テスト用ユーザーと関連データは終了時に削除されます。

```bash
export TEST_DATABASE_URL="postgresql://user:password@host:5432/equa_test"
python3 -m unittest tests.test_postgres_integration -v
```

## CSV対応銀行

| 金融機関 | CSV | 状態 |
|---|---|---|
| Sony銀行 | 普通預金・入出金CSV | 対応済み |
| Sony銀行 | 振込CSV | 対応済み |
| 楽天銀行 | Parser雛形 | 未対応 |
| 三井住友銀行 | Parser雛形 | 未対応 |
| 三菱UFJ銀行 | Parser雛形 | 未対応 |
| ゆうちょ銀行 | Parser雛形 | 未対応 |
| 住信SBIネット銀行 | Parser雛形 | 未対応 |
| 楽天カード | Parser雛形 | 未対応 |
| 汎用CSV | Parser雛形 | 未対応 |

Sony銀行CSVはUTF-8とShift_JIS（CP932）に対応しています。共通形式は`date`、`description`、`amount`、`type`、`balance`、`category`です。

```csv
取引日,摘要,参考情報,通貨,預入額,引出額,差引残高
2026/08/01,給与振込,8月分,JPY,"200,000",,"1,000,000"
2026/08/02,コンビニ利用,,JPY,,"1,250","998,750"
```

## データ互換性と注意事項

- 既存の`kakeibo.db`は削除しません。移行スクリプトでPostgreSQLへコピーできます。
- `DATABASE_URL`未設定時の新規ローカルDBは`local.db`です。
- 旧`kakeibo.csv`と`budgets.json`は、SQLiteが空の場合に自動移行します。
- Version 2以前のインポート履歴は取引との関連情報がないため、安全のためCSV単位取消を無効化します。
- `local.db`、`kakeibo.db`、CSV、環境変数ファイル、ビルド成果物はGit管理対象外です。

## プロジェクト構成

```text
kakeibo-app/
├── app.py
├── database.py
├── gui_app.py
├── web/
│   ├── app.py
│   ├── parsers/
│   ├── templates/
│   └── static/
├── tests/
├── scripts/
│   └── migrate_sqlite_to_postgres.py
├── requirements.txt
├── requirements-web.txt
├── requirements-build.txt
├── render.yaml
├── railway.json
├── Procfile
├── CHANGELOG.md
└── README.md
```

## ロードマップ

- [ ] Sony銀行以外の銀行・カードParserを実装
- [ ] 取引の編集と一括操作
- [ ] カテゴリー別予算とアラート
- [ ] CSV・PDFレポートのエクスポート
- [ ] 定期収支の自動登録
- [ ] 検索条件とダッシュボード設定の保存
- [ ] Alembicによる本番スキーマバージョン管理
- [ ] macOSアプリのコード署名・公証

## ライセンス

現在、このリポジトリにはオープンソースライセンスを設定していません。再配布・改変・商用利用を希望する場合は、リポジトリ所有者へ確認してください。

変更履歴は[CHANGELOG.md](CHANGELOG.md)を参照してください。
