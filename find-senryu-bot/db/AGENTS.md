<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# db

## Purpose
データベース接続の初期化、スキーママイグレーション、および暗号化データマイグレーションを担当するパッケージです。SQLite3とPostgreSQLの両方をサポートし、SQLマイグレーションファイルはバイナリに埋め込まれます。

## Key Files

| File | Description |
|------|-------------|
| `db.go` | `Init()` / `Migrate()` / `Close()` / `GetStats()` — DB接続とマイグレーションのコア実装 |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `migrations/` | SQLマイグレーションファイル（see `migrations/AGENTS.md`） |

## For AI Agents

### Working In This Directory
- `Init()` はシングルトン（`sync.Once`）。テスト間で再利用される点に注意
- マイグレーションファイルは `//go:embed` でバイナリに埋め込まれるため、`go build` 時に自動で含まれる
- 暗号化マイグレーション（`migrateEncryptSenryuData`）はべき等設計：起動のたびに実行され、未暗号化レコードのみを処理する
- SQLiteはWALモードを有効化（`PRAGMA journal_mode=WAL`）してコンカレンシーを改善
- 暗号化キーなしでDB内に暗号化済みデータが存在する場合、起動を拒否する（データ破損防止）

### Testing Requirements
- DBテストはテスト用DBファイルまたはインメモリSQLiteを使用すること

### Common Patterns
- カーソルベースページネーション（`WHERE id > ?`）でバッチ処理
- バッチ処理はトランザクションでラップし、失敗時は `Rollback()`

## Dependencies

### Internal
- `config/` — DB接続設定
- `model/` — GORMモデル
- `pkg/crypto/` — データ暗号化
- `pkg/logger/` — ロギング

### External
- `github.com/jinzhu/gorm` — ORM
- `github.com/golang-migrate/migrate/v4` — マイグレーション
- `github.com/mattn/go-sqlite3` — SQLiteドライバ
- `github.com/lib/pq` — PostgreSQLドライバ

<!-- MANUAL: -->
