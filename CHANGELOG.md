# Changelog

EQUAの変更履歴はこのファイルに記録します。

## [Unreleased]

### Added

- SQLAlchemy 2によるSQLite / PostgreSQL共通データ層
- 全テーブルをSQLiteからPostgreSQLへ移す移行スクリプト
- Render Blueprintで作成するPostgreSQLと`DATABASE_URL`の自動接続設定

### Changed

- `DATABASE_URL`設定時はPostgreSQL、未設定時は`local.db`を使用する構成へ変更
- Render・Railway・ローカル環境のデータベース設定手順をREADMEへ追加

### Fixed

- Render Blueprintを既存`kakeibo-db`の参照専用にし、別PostgreSQLの意図しない作成を防止
- Renderで`DATABASE_URL`がない場合の一時SQLiteへのフォールバックを禁止
- 起動ログと診断スクリプトに接続先DB・ユーザー件数・取引件数を追加
- Render起動ログへ`DATABASE_URL`の有無とパスワードを伏せたSQLAlchemy接続URLを追加
- 旧Render永続ディスクのSQLiteからユーザーを復元する手順をREADMEへ追加
- UTCで保存されたCSVインポート履歴の日時を画面表示時に日本時間（JST）へ変換
- 今後の日時表示でも利用できる`zoneinfo`ベースの共通日時ユーティリティを追加
- Render Web Serviceの`DATABASE_URL`参照先を既存の`kakeibo-db`へ修正
- iPhone Safari・Android Chromeで月別資産推移の高さが不足する問題を修正
- Chart.js用の親要素に320px以上の高さを確保し、画面変更時に安全に再生成
- 資産残高データがない場合の中央メッセージ表示を追加
- Service Workerのキャッシュ名を更新し、スマートフォンの旧CSS・JavaScriptを破棄

## [v2.0.0] - 2026-08-02

### Added

- Version 2の累計統計カード
- 複数銀行口座に対応した資産カードと合計資産
- Chart.jsによる全期間の月別資産推移・月別収支推移
- 全期間の支出カテゴリーランキング
- 年別の収入・支出・貯蓄額・貯蓄率・収支・前年比レポート
- 日付・店舗名/メモ・カテゴリー・金額・銀行の部分一致検索
- 収入・支出・振込・カード・現金・カテゴリー・銀行フィルター
- CSV履歴とTransactionの関連付け、CSV単位の取込取消
- 集計結果のキャッシュと更新時の自動無効化
- Render・Railway・Gunicorn用のデプロイ設定
- 全画面の `Version 2.0.0` 表示

### Changed

- 累計統計、資産一覧、インポート履歴を共通のカードUIへ統一
- カード間隔・高さ・余白・モバイル表示を調整
- `EQUA_DATA_DIR` でSQLiteの永続化先を指定可能に変更

### Fixed

- Sony銀行CSVの預入額・引出額・支払額から `Transaction.type` を正しく保存
- 収入件数・支出件数を実際に保存した `Transaction.type` から集計
- 普通預金CSVと振込CSVの追加取込・重複判定・残高統合
- CSV取込取消後に口座残高・収支・カテゴリー・グラフのキャッシュを再計算

### Compatibility

- 既存SQLite DBは削除せず、必要な列とインデックスだけを自動追加
- Sony銀行の普通預金・入出金・振込CSVと従来の重複判定を維持
- Version 2以前の履歴は取引との関連情報がないため、誤削除防止のためCSV単位取消を無効化

## [1.x]

- Flask/PWA版、ログイン、Sony銀行CSV Parser、資産台帳、ダッシュボードを追加
- Tkinterデスクトップ版とSQLiteデータを共有
