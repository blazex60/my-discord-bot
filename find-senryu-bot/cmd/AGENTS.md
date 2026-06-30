<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# cmd

## Purpose
スタンドアロン実行バイナリのエントリポイントを格納するディレクトリです。Goの慣例に従い、各サブディレクトリが独立したバイナリとしてビルドされます。

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `migrate/` | DBマイグレーション専用バイナリ（see `migrate/AGENTS.md`） |

## For AI Agents

### Working In This Directory
- 新しいCLIツールを追加する場合は `cmd/<name>/main.go` として作成する
- 各サブディレクトリは `package main` を持つ独立したバイナリ

### Common Patterns
- `go build ./cmd/migrate` でマイグレーションバイナリをビルド

<!-- MANUAL: -->
