<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# cmd/migrate

## Purpose
データベースマイグレーションをBotプロセスとは独立して実行するためのスタンドアロンバイナリです。設定を読み込み、暗号化を初期化し、`db.Migrate()` を実行して終了します。

## Key Files

| File | Description |
|------|-------------|
| `main.go` | マイグレーション専用エントリポイント |

## For AI Agents

### Working In This Directory
- ビルド: `go build -o migrate ./cmd/migrate`
- 実行には `config.toml` が必要（または `FINDSENRYU_` 環境変数）
- 暗号化キーが設定されている場合、既存の平文データを自動暗号化する
- Botを停止せずにマイグレーションだけ実行したい場合に使用する

### Common Patterns
- 起動順序: config → logger → crypto → db.Init() → db.Migrate()
- エラー時は `os.Exit(1)` で非ゼロ終了

## Dependencies

### Internal
- `config/` — 設定読み込み
- `db/` — DB初期化とマイグレーション実行
- `pkg/crypto/` — 暗号化初期化
- `pkg/logger/` — ロギング

<!-- MANUAL: -->
