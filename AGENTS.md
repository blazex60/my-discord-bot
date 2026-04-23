<!-- Generated: 2026-04-23 | Updated: 2026-04-23 -->

# my-discord-bot

## Purpose

複数の Discord Bot を管理するモノレポ。各ボットは独立したサブディレクトリに格納され、
独自の依存関係・設定・CLAUDE.md・AGENTS.md を持つ。ボット間でコードを共有しない。

## Key Files

| File | Description |
|------|-------------|
| `CLAUDE.md` | Claude Code へのリポジトリ共通指示 |
| `README.md` | リポジトリ概要（人間向け） |
| `DAVE_LIMITATION.md` | GTX 980 Ti (VRAM 6GB) 環境での制限事項メモ |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `discord-minutes-bot/` | Discord VC 録音 → オフライン ASR/LLM → 議事録自動生成（see `discord-minutes-bot/AGENTS.md`） |
| `chat-summary-bot/` | 雑談チャンネルのテキスト要約・話題検索・追いつきサポート（see `chat-summary-bot/AGENTS.md`） |

## For AI Agents

### Working In This Directory

- ボットを横断する変更は行わない。各ボットのディレクトリ内の CLAUDE.md と AGENTS.md を必ず参照してから作業する
- シークレット（DISCORD_TOKEN 等）はソースコードに絶対に書かない。各ボットの `.env` で管理する
- 外部 AI API（OpenAI API、Anthropic API 等）は使用しない（両ボット共通の禁止事項）

### Testing Requirements

各ボット独自のテスト手順に従う（各サブディレクトリの AGENTS.md 参照）。

### Common Patterns

- パッケージ管理: `uv`（両ボットとも）
- フォーマット/リント: `ruff format .` / `ruff check .`（両ボットとも）

## Dependencies

### External

| パッケージ | 用途 |
|---|---|
| `py-cord` | 両ボットの Discord Bot フレームワーク |
| `uv` | Python パッケージ管理ツール |

<!-- MANUAL: リポジトリ全体のメモはここ以降に追記 -->
