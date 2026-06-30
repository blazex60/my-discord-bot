<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# db/migrations/postgres

## Purpose
PostgreSQL用のSQLマイグレーションファイルを格納します。`db.go` の `//go:embed` により `postgresMigrations` 変数としてバイナリに埋め込まれます。

## Key Files

| File | Description |
|------|-------------|
| `000001_create_tables.up.sql` | 初期テーブル作成（senryu, muted_channels 等） |
| `000002_backfill_spoiler.up.sql` | spoilerカラムのバックフィル |
| `000003_create_metadata.up.sql` | metadataテーブル作成 |
| `000004_add_set_by_to_detection_opt_outs.up.sql` | detection_opt_outsにset_byカラム追加 |

## For AI Agents

### Working In This Directory
- 新規マイグレーション追加時は `sqlite3/` にも **必ず同等のファイルを追加** すること
- PostgreSQL構文を使用（`SERIAL`, `ON CONFLICT DO UPDATE` など）
- ファイル追加後は `go build ./...` で埋め込みを更新する必要がある

<!-- MANUAL: -->
