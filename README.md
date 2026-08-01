<div align="center">
  <img src="assets/app_icon.png" alt="かんたん家計簿のアプリアイコン" width="140">

  # かんたん家計簿

  **毎日の支出を、見やすくシンプルに管理するデスクトップアプリ**

  [![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
  [![GUI](https://img.shields.io/badge/GUI-Tkinter-3B82F6)](https://docs.python.org/3/library/tkinter.html)
  [![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows-111827)](#起動方法)
  [![License](https://img.shields.io/badge/License-Not%20specified-94A3B8)](#ライセンス)
</div>

## アプリについて

「かんたん家計簿」は、PythonとTkinterで作ったダッシュボード付き家計簿アプリです。
支出を入力すると、今月の支出や残り予算、カテゴリ別の割合、月ごとの推移を
ホーム画面ですぐに確認できます。

ダークテーマと大きなボタンを採用し、macOSやWindowsのデスクトップアプリとして
直感的に操作できるデザインを目指しています。入力したデータが外部サービスへ
送信されることはありません。

## スクリーンショット

<!--
  スクリーンショットを追加するときは、画像を次の場所へ保存してください。

  docs/screenshots/dashboard.png
  docs/screenshots/charts.png

  保存後、このコメントを削除し、下のコメントアウトを解除してください。

  <p align="center">
    <img src="docs/screenshots/dashboard.png" alt="ダッシュボード画面" width="820">
  </p>

  | ダッシュボード | グラフ画面 |
  |:--:|:--:|
  | ![ダッシュボード](docs/screenshots/dashboard.png) | ![グラフ](docs/screenshots/charts.png) |
-->

> スクリーンショットは準備中です。画像は `docs/screenshots/` に追加予定です。

## 機能一覧

### ダッシュボード

- 今月の支出、予算、残り予算をカード表示
- 一番支出が多いカテゴリを表示
- 前月からの増減率を表示
- 今月のカテゴリ別支出を円グラフで表示
- 直近6か月の支出を棒グラフで表示

### 支出管理

- 日付、カテゴリ、金額、メモを入力して支出を登録
- 支出を月別または全期間で一覧表示
- カテゴリ別の合計金額を表示
- 選択した支出を確認後に削除
- 日付や金額の入力エラーをダイアログで通知

### 予算・グラフ

- 月ごとの予算を設定して保存
- 指定月のカテゴリ別円グラフを別ウィンドウで表示
- 直近12か月の棒グラフを別ウィンドウで表示
- ウィンドウサイズに合わせてグラフを自動調整

### デスクトップアプリ

- ダークテーマとカテゴリ別カラー
- macOS向けアプリアイコン
- PyInstallerによる `.app` ビルド
- Finderからのダブルクリック起動

## 起動方法

### 必要環境

- Python 3.10以降
- Tkinter
- macOSまたはWindows

Python公式インストーラーを使用している場合、通常はTkinterも同梱されています。
アプリの実行に外部Pythonライブラリは必要ありません。

### 1. リポジトリを取得

```bash
git clone https://github.com/fearless0712/kakeibo-app.git
cd kakeibo-app
```

### 2. GUI版を起動

```bash
python3 gui_app.py
```

Windowsで `python3` が認識されない場合は、次のコマンドを使用してください。

```powershell
python gui_app.py
```

### ターミナル版を起動

以前のターミナル版も利用できます。

```bash
python3 app.py
```

## Macアプリのビルド

macOS上でPyInstallerを使うと、Finderからダブルクリックで起動できる
`かんたん家計簿.app` を作成できます。

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-build.txt
./scripts/build_macos.sh
```

ビルドされたアプリは次の場所に出力されます。

```text
dist/かんたん家計簿.app
```

配布版で入力したデータは、アプリを更新しても消えないよう、次の場所へ保存されます。

```text
~/Library/Application Support/Kakeibo/
```

> [!NOTE]
> 現在のアプリはコード署名・公証を行っていません。別のMacで初めて開く場合は、
> Controlキーを押しながらアプリをクリックして「開く」を選ぶ必要があります。

## 使用技術

| 技術 | 用途 | 状態 |
|---|---|---|
| Python 3 | アプリケーション全体の処理 | 使用中 |
| Tkinter / ttk | GUI、ダークテーマ、表、グラフ描画 | 使用中 |
| CSV / JSON | 支出データと月別予算のローカル保存 | 使用中 |
| PyInstaller | macOSアプリのパッケージ作成 | 使用中 |
| Pillow | ビルド時のアプリアイコン変換 | 使用中 |
| SQLite | 支出データのデータベース管理 | 今後移行予定 |

> [!IMPORTANT]
> 現在の保存方式はCSVとJSONです。SQLiteはまだ実装されておらず、今後の
> データ検索・編集機能の拡張に合わせて移行する予定です。

## プロジェクト構成

```text
kakeibo-app/
├── app.py                  # データ操作とターミナル版
├── gui_app.py              # GUI版アプリ
├── assets/
│   └── app_icon.png        # アプリアイコン
├── scripts/
│   └── build_macos.sh      # macOS用ビルドスクリプト
├── kakeibo.spec            # PyInstaller設定
├── requirements-build.txt  # ビルド用ライブラリ
└── README.md
```

実行時に作られる `kakeibo.csv` と `budgets.json` は個人データを含むため、
Gitの管理対象から除外しています。

## 今後追加予定の機能

- [ ] CSV / JSONからSQLiteへのデータ移行
- [ ] 登録済み支出の編集
- [ ] 収入の登録と収支管理
- [ ] 年間レポートとカテゴリ別予算
- [ ] CSVのインポート・エクスポート
- [ ] 定期支出の自動登録
- [ ] 検索・並べ替え・詳細フィルター
- [ ] Windows向け実行ファイルの配布
- [ ] macOSアプリのコード署名と公証
- [ ] テストコードの追加

## データについて

ソースコードから起動した場合、支出は `kakeibo.csv`、予算は `budgets.json` に
保存されます。これらのファイルには個人情報が含まれる可能性があるため、共有や
Gitへの追加には注意してください。

## ライセンス

ライセンスは現在指定されていません。再配布や商用利用を検討する場合は、
リポジトリ所有者へ確認してください。
