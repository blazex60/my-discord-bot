<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# commands

## Purpose
Discordスラッシュコマンドのハンドラ実装を格納するパッケージです。各ファイルがコマンドに対応し、`main.go` の `commandHandlers` マップから呼び出されます。管理者コマンドは `admin.go` に集約されています。

## Key Files

| File | Description |
|------|-------------|
| `admin.go` | `/admin stats/guilds/backup/admin-role` コマンドハンドラと `AdminCommands()` 定義 |
| `admin_test.go` | admin コマンドのテスト |
| `channel.go` | `/channel` コマンド — チャンネルタイプ別検出設定のUIパネル |
| `contact.go` | `/contact` コマンド — モーダル経由で管理者へ問い合わせ送信 |
| `delete.go` | `/delete` コマンド — 川柳の選択削除 |
| `delete_test.go` | delete コマンドのテスト |
| `detect.go` | `/detect on/off/status/ban/unban/list` コマンド |
| `doctor.go` | `/doctor` コマンド — Bot動作診断 |
| `help.go` | `/help` コマンド — コマンド一覧とWebドキュメントへのリンクを表示 |
| `mute.go` | `/mute` `/unmute` コマンドハンドラ |
| `welcome.go` | ギルド参加時ウェルカムメッセージ送信ロジック |
| `welcome_test.go` | welcome ロジックのテスト |

## For AI Agents

### Working In This Directory
- 各ハンドラは `(s *discordgo.Session, i *discordgo.InteractionCreate)` シグネチャを持つ
- 管理者コマンドは `admin.go` の `AdminCommands()` で定義し、`main.go` でギルド限定登録される
- `admin.go` 内の権限チェックは `pkg/permissions` と `service` の `GetGuildAdminRole` を組み合わせてロールベース判定を行う
- バックアップマネージャと起動時刻は `SetBackupManager()` / `SetStartTime()` で外部から注入される

### Testing Requirements
- `go test ./commands/...` でコマンドテスト実行

### Common Patterns
- インタラクションに対するレスポンスは `s.InteractionRespond()` を使用
- エラー時は ephemeral（本人のみ表示）メッセージで返す

## Dependencies

### Internal
- `db/` — DBアクセス
- `model/` — データモデル
- `service/` — ビジネスロジック
- `pkg/adminnotify/` — 管理者通知
- `pkg/backup/` — バックアップ操作
- `pkg/permissions/` — 権限チェック

### External
- `github.com/bwmarrin/discordgo` — Discord API

<!-- MANUAL: -->
