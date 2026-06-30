<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# FindSenryu4Discord

## Purpose
Discordサーバー上のメッセージから5-7-5の音節パターン（川柳）を自動検出・記録するDiscord Botです。Goで実装されており、シャーディング対応のDiscordセッション管理、SQLite/PostgreSQL両対応のDB、AES-256-GCM暗号化、Prometheusメトリクスなどを備えます。

## Key Files

| File | Description |
|------|-------------|
| `main.go` | エントリポイント。シャーディング、コマンド登録、イベントハンドラ初期化 |
| `main_test.go` | メインロジックのテスト |
| `go.mod` | Goモジュール定義（module: `github.com/u16-io/FindSenryu4Discord`） |
| `go.sum` | 依存関係ロックファイル |
| `Dockerfile` | コンテナビルド定義 |
| `compose.yaml` | Docker Compose定義 |
| `sample.config.toml` | 設定ファイルテンプレート |
| `LICENSE` | MITライセンス |
| `README.md` | プロジェクト概要・コマンド一覧・セルフホスト手順 |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `cmd/` | スタンドアロン実行バイナリ（see `cmd/AGENTS.md`） |
| `commands/` | Discordスラッシュコマンドハンドラ（see `commands/AGENTS.md`） |
| `config/` | 設定読み込み・バリデーション（see `config/AGENTS.md`） |
| `db/` | データベース初期化・マイグレーション・クエリ（see `db/AGENTS.md`） |
| `model/` | GORMモデル定義（see `model/AGENTS.md`） |
| `pkg/` | 再利用可能な共有パッケージ（see `pkg/AGENTS.md`） |
| `service/` | ビジネスロジック層（see `service/AGENTS.md`） |

## For AI Agents

### Working In This Directory
- `main.go` はシャーディングロジック、イベントハンドラ登録、コマンド登録の中心点
- グローバルスラッシュコマンドは `userCommands` スライスで定義
- 管理者コマンドは `commands.AdminCommands()` から取得し、`admin.guild_id` のギルドにのみ登録
- 設定は `FINDSENRYU_` プレフィックスの環境変数でオーバーライド可能

### Testing Requirements
- `go test ./...` でテスト実行
- `main_test.go` は統合的なテストを含む

### Common Patterns
- シャード0をプライマリセッションとして使用（コマンド登録等）
- 起動順序: config → logger → crypto → db → health → backup → Discord sessions → commands

## Dependencies

### External
- `github.com/bwmarrin/discordgo v0.29.0` — Discord API クライアント
- `github.com/0x307e/go-haiku` — 俳句/川柳検出ライブラリ
- `github.com/ikawaha/kagome-dict/uni` — 日本語形態素解析辞書
- `github.com/jinzhu/gorm v1.9.16` — ORM
- `github.com/golang-migrate/migrate/v4` — DBマイグレーション
- `github.com/knadh/koanf/v2` — 設定管理
- `github.com/prometheus/client_golang` — Prometheusメトリクス
- `github.com/cockroachdb/errors` — エラーハンドリング

<!-- MANUAL: -->
