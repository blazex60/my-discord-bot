<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# db/migrations

## Purpose
`golang-migrate` 形式のSQLマイグレーションファイルを格納するディレクトリです。DB方言ごとにサブディレクトリを分け、`db.go` の `//go:embed` でバイナリに埋め込まれます。

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `postgres/` | PostgreSQL用マイグレーションSQL（see `postgres/AGENTS.md`） |
| `sqlite3/` | SQLite3用マイグレーションSQL（see `sqlite3/AGENTS.md`） |

## For AI Agents

### Working In This Directory
- 新しいマイグレーションを追加する場合は **両方のディレクトリ** に対応するSQLファイルを追加すること
- ファイル命名規則: `000005_description.up.sql`（連番を必ず上げる）
- `golang-migrate` は `.down.sql` も対象外だが、必要に応じてロールバック用に作成しても良い
- マイグレーションはバイナリに埋め込まれるため、ファイル追加後は再ビルドが必要

### Common Patterns
- `up.sql` のみ実装（ダウンマイグレーションは現状未使用）
- SQLiteとPostgreSQLの構文差異（例: `AUTOINCREMENT` vs `SERIAL`）に注意

<!-- MANUAL: -->
