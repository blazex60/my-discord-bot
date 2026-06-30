<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# service

## Purpose
ビジネスロジック層。DBアクセスとドメインロジックを組み合わせ、コマンドハンドラ（`commands/`）が直接DBを触らずに済む抽象化を提供します。

## Key Files

| File | Description |
|------|-------------|
| `admin_role.go` | ギルドごとの管理ロールID取得・設定・削除（Metadataテーブル経由） |
| `admin_role_test.go` | admin_role のテスト |
| `channel_config.go` | チャンネルタイプ別検出設定の取得・更新 |
| `channel_config_test.go` | channel_config のテスト |
| `contact.go` | お問い合わせ送信ロジック |
| `contact_test.go` | contact のテスト |
| `detection.go` | ユーザーオプトアウト登録・解除・確認ロジック |
| `detection_test.go` | detection のテスト |
| `mute.go` | チャンネルミュート登録・解除ロジック |
| `senryu.go` | 川柳の保存・検索・削除・暗号化/復号ラッパー |
| `senryu_test.go` | senryu のテスト |

## For AI Agents

### Working In This Directory
- 各関数は `metrics.RecordDatabaseOperation()` と `metrics.RecordError()` を適切に呼び出すこと
- 管理ロールIDは `model.Metadata` テーブルにキー `admin_role:<guildID>` で保存される
- 川柳の保存時は `crypto.Encrypt()` を通じて自動暗号化（暗号化が有効な場合のみ）

### Testing Requirements
- `go test ./service/...` でサービステスト実行

### Common Patterns
- DBエラーは `errors.Wrap()` でラップしてからreturn
- `gorm.IsRecordNotFoundError(err)` で「存在しない」ケースを区別

## Dependencies

### Internal
- `db/` — データベースハンドル (`db.DB`)
- `model/` — データモデル
- `pkg/crypto/` — 暗号化・復号
- `pkg/logger/` — ロギング
- `pkg/metrics/` — メトリクス記録

<!-- MANUAL: -->
