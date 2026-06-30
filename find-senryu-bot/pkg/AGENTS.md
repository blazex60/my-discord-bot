<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# pkg

## Purpose
プロジェクト全体で再利用される独立したパッケージ群のコンテナです。各サブパッケージは単一の責務を持ち、相互依存を最小限に抑えた設計になっています。

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `adminnotify/` | 管理者通知（ギルド参加/脱退・日次サマリー）（see `adminnotify/AGENTS.md`） |
| `backup/` | SQLiteデータベースの自動バックアップ（see `backup/AGENTS.md`） |
| `crypto/` | AES-256-GCM暗号化・復号（see `crypto/AGENTS.md`） |
| `health/` | ヘルスチェックHTTPサーバー（see `health/AGENTS.md`） |
| `logger/` | 構造化ロギング（see `logger/AGENTS.md`） |
| `metrics/` | Prometheusメトリクス収集（see `metrics/AGENTS.md`） |
| `permissions/` | Bot管理者権限チェック（see `permissions/AGENTS.md`） |

## For AI Agents

### Working In This Directory
- 新しい共有機能は `pkg/` に新サブパッケージとして追加すること
- 各パッケージは `commands/` や `service/` に依存しない（依存方向: pkg ← service ← commands）

<!-- MANUAL: -->
