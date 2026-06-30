<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# pkg/logger

## Purpose
プロジェクト全体で使用する構造化ロガーを提供するパッケージです。JSON/テキスト形式とログレベル（debug/info/warn/error）を設定可能なグローバルロガーを初期化します。

## Key Files

| File | Description |
|------|-------------|
| `logger.go` | `Init()` / `Debug()` / `Info()` / `Warn()` / `Error()` グローバル関数 |

## For AI Agents

### Working In This Directory
- `Init(Config{Level, Format})` を起動時に一度だけ呼び出す
- 他パッケージからは `logger.Info("msg", "key", val)` の形式で使用（key-valueペア）
- JSON形式は本番環境向け、テキスト形式は開発向け

### Common Patterns
- `slog` パッケージベースの実装
- フィールドは `"key", value` の可変長引数で渡す

<!-- MANUAL: -->
