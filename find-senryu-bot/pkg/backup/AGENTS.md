<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# pkg/backup

## Purpose
SQLiteデータベースの定期自動バックアップを管理するパッケージです。設定された間隔でファイルコピーを行い、最大保持数を超えた古いバックアップを自動削除します。

## Key Files

| File | Description |
|------|-------------|
| `backup.go` | `Manager` 構造体、`NewManager()` / `Start()` / `Stop()` / `RunBackup()` |

## For AI Agents

### Working In This Directory
- SQLite専用。PostgreSQL使用時はバックアップマネージャは初期化されない（`main.go` の条件分岐参照）
- バックアップは `config.Backup.Path` ディレクトリにタイムスタンプ付きファイル名で保存
- `config.Backup.MaxBackups` を超えた古いファイルは自動削除
- `/admin backup` コマンドから手動実行も可能（`commands.SetBackupManager()` で注入）

### Common Patterns
- バックグラウンドgoroutineでタイマーループを実行
- `stopCh` チャネルによるグレースフルシャットダウン

## Dependencies

### Internal
- `config/` — バックアップ設定（パス・間隔・最大数）
- `pkg/logger/` — ロギング

<!-- MANUAL: -->
