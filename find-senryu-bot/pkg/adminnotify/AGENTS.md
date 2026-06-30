<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# pkg/adminnotify

## Purpose
Bot管理者への通知を管理するパッケージです。ギルド参加/脱退のリアルタイム通知と、毎日の稼働サマリーを管理チャンネルに送信します。シャーディング環境での全セッションを横断したギルド数・ユーザー数集計をサポートします。

## Key Files

| File | Description |
|------|-------------|
| `adminnotify.go` | `Manager` 構造体、`NewManager()` / `SetAllSessions()` / 通知送信ロジック |

## For AI Agents

### Working In This Directory
- `Manager` は `main.go` で初期化され、`SetAllSessions()` で全シャードセッションを受け取る
- `logChannelID` はリアルタイム通知（ギルド参加/脱退）用
- `reportChannelID` は日次サマリー用（未設定なら `logChannelID` にフォールバック）
- ギルド数・ユーザー数は全シャードの `session.State.Guilds` を合算して計算する

### Common Patterns
- `stopCh` / `stoppedCh` チャネルによるグレースフルシャットダウン

## Dependencies

### Internal
- `service/` — 川柳統計取得
- `pkg/logger/` — ロギング

### External
- `github.com/bwmarrin/discordgo` — Discord メッセージ送信

<!-- MANUAL: -->
