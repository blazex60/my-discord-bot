<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# db/migrations/sqlite3

## Purpose
SQLite3用のSQLマイグレーションファイルを格納します。`db.go` の `//go:embed` により `sqliteMigrations` 変数としてバイナリに埋め込まれます。

## Key Files

| File | Description |
|------|-------------|
| `000001_create_tables.up.sql` | 初期テーブル作成（senryu, muted_channels 等） |
| `000002_backfill_spoiler.up.sql` | spoilerカラムのバックフィル |
| `000003_create_metadata.up.sql` | metadataテーブル作成 |
| `000004_add_set_by_to_detection_opt_outs.up.sql` | detection_opt_outsにset_byカラム追加 |

## For AI Agents

### Working In This Directory
- 新規マイグレーション追加時は `postgres/` にも **必ず同等のファイルを追加** すること
- SQLite構文を使用（`AUTOINCREMENT`, `INSERT OR IGNORE` など）
- PostgreSQLとの構文差異に注意: `SERIAL` → `INTEGER PRIMARY KEY AUTOINCREMENT`
- ファイル追加後は `go build ./...` で埋め込みを更新する必要がある

<!-- MANUAL: -->
