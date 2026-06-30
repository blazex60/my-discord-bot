<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# pkg/health

## Purpose
ヘルスチェックとPrometheusメトリクスを提供するHTTPサーバーを起動するパッケージです。コンテナオーケストレーター（Kubernetes等）からのLiveness/Readinessプローブに応答します。

## Key Files

| File | Description |
|------|-------------|
| `health.go` | `StartServer()` — `/health` / `/ready` / `/stats` / `/metrics` エンドポイント |

## For AI Agents

### Working In This Directory
- デフォルトポートは `9090`（`config.Server.Port` で変更可）
- `config.Server.Enabled = false` で無効化可能
- `/health` — 常に200を返す（プロセス生存確認）
- `/ready` — DBとDiscord接続が確立済みの場合に200
- `/stats` — JSON形式の稼働統計
- `/metrics` — Prometheusスクレイプエンドポイント

### Common Patterns
- `http.DefaultServeMux` を使わず専用 `ServeMux` を作成してルーティング

## Dependencies

### Internal
- `config/` — サーバー設定
- `db/` — DB接続状態確認
- `pkg/logger/` — ロギング
- `pkg/metrics/` — Prometheusハンドラ

<!-- MANUAL: -->
