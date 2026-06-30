<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# pkg/metrics

## Purpose
Prometheusメトリクスの定義と記録関数を提供するパッケージです。DB操作回数、エラー数、川柳検出数などを収集し、`/metrics` エンドポイントで公開します。

## Key Files

| File | Description |
|------|-------------|
| `metrics.go` | カウンタ・ゲージ定義と `RecordDatabaseOperation()` / `RecordError()` / `RecordSenryuDetected()` 等 |

## For AI Agents

### Working In This Directory
- 新しいメトリクスを追加する場合は `var` ブロックに `prometheus.NewCounter` 等を追加し、`init()` で `prometheus.MustRegister()` する
- `service/` の各関数冒頭で `metrics.RecordDatabaseOperation("操作名")` を呼び出すパターン

### Common Patterns
- メトリクス名は `findsenryu_` プレフィックスを使用

## Dependencies

### External
- `github.com/prometheus/client_golang` — Prometheusクライアント

<!-- MANUAL: -->
