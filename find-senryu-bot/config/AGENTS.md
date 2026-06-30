<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# config

## Purpose
TOMLファイルと環境変数から設定を読み込み、型付き構造体として提供するパッケージです。シングルトンパターン（`sync.Once`）で一度だけロードされます。

## Key Files

| File | Description |
|------|-------------|
| `config.go` | `Config` 構造体定義、`Load()` / `GetConf()` / デフォルト値設定・バリデーション |

## For AI Agents

### Working In This Directory
- `Load("config.toml")` はべき等。2回目以降は `once.Do` によりスキップされる
- 環境変数は `FINDSENRYU_` プレフィックス + アンダースコアをドット区切りに変換（例: `FINDSENRYU_DISCORD_TOKEN` → `discord.token`）
- 新しい設定項目を追加する場合は `Config` 構造体、`setDefaults()`、必要なら `validate()` を更新する

### Common Patterns
- 他パッケージからは `config.GetConf()` でシングルトンを取得
- 必須フィールド不足時は `validate()` がエラーを返しプロセスが終了する

## Dependencies

### External
- `github.com/knadh/koanf/v2` — 多ソース設定管理
- `github.com/knadh/koanf/parsers/toml` — TOMLパーサー
- `github.com/knadh/koanf/providers/env` — 環境変数プロバイダー
- `github.com/knadh/koanf/providers/file` — ファイルプロバイダー

<!-- MANUAL: -->
