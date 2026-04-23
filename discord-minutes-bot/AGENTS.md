<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-23 | Updated: 2026-04-23 -->

# discord-minutes-bot

## Purpose

Discord VC の音声をローカル Linux 環境で完全オフライン処理し、Markdown 形式の議事録を自動生成する Bot。
フェーズ直列実行・メモリ排他制御を中心とした設計で、VRAM 6GB (GTX 980 Ti) 環境での安定動作を最優先とする。

---

## Key Files

| File | Description |
|------|-------------|
| `bot.js` | Discord Bot エントリーポイント。録音・バッチパイプライン・スラッシュコマンド定義を含む Node.js メインファイル |
| `main.py` | Python エントリーポイント（スタブ。実処理は pipeline/ と utils/ が担う） |
| `config.yaml` | ASR・LLM・ストレージ・Discord 設定。シークレットは記載しない |
| `.env.example` | DISCORD_TOKEN 等のシークレットテンプレート |
| `pyproject.toml` | Python 依存関係（uv 管理） |
| `package.json` | Node.js 依存関係（discord.js / @discordjs/voice） |
| `spec_v04.md` | 設計仕様書 v0.4 |
| `CLAUDE.md` | Claude Code 向けの詳細実装ガイドライン |

---

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `pipeline/` | ASR (transcriber.py) と LLM 要約 (summarizer.py) のサブプロセスモジュール（see `pipeline/AGENTS.md`） |
| `utils/` | チャンク分割 (chunker.py) とモデルアンロード (memory.py) のユーティリティ（see `utils/AGENTS.md`） |
| `tests/` | pytest テストスイート（see `tests/AGENTS.md`） |
| `tmp/recordings/` | VC 録音の WAV ファイル置き場（`{sessionId}_{userId}.wav`、処理後に削除） |
| `tmp/transcripts/` | ASR トランスクリプト・チャットログ・メタデータの一時置き場（処理後に削除） |
| `output/` | 生成済み議事録 Markdown（`minutes_{sessionId}.md`、自動削除しない） |
| `models/` | GGUF モデルファイル置き場（.gitignore 対象） |
| `logs/` | 実行ログ |

---

## Architecture

### パイプライン全体（直列・フェーズ分離）

```
[フェーズ1] 録音 — bot.js
  Discord VC → @discordjs/voice → PCM バッファ → WAV ファイル書き出し
  tmp/recordings/{sessionId}_{userId}.wav

[フェーズ2] ASR — pipeline/transcriber.py（subprocess）
  Whisper large-v3 (CUDA) → OOM 時 medium → CPU フォールバック
  出力: tmp/transcripts/{sessionId}_transcript.txt

[フェーズ3] LLM 要約 — pipeline/summarizer.py（subprocess）
  Gemma-4-26B GGUF → チャンク分割 → 2段階要約 → Markdown
  出力: output/minutes_{sessionId}.md

[フェーズ4] 出力 — bot.js
  Discord へ議事録ファイルを送信 → tmp/ の一時ファイルを削除
```

### Discord コマンド一覧

| コマンド | 動作 |
|---|---|
| `/record_start` | VC に参加して録音を開始する |
| `/record_stop` | 録音を停止してバッチ処理を開始する |
| `/transcribe_only` | 既存 WAV から ASR・要約のみ再実行する（録音失敗時の再開用） |

### セッション ID

`YYYYMMDD_HHMMSS` 形式。ファイル名プレフィックスに使用する。

---

## For AI Agents

### Working In This Directory

- **Node.js 部分 (bot.js)**: npm / package.json で管理。録音・コマンドハンドリングを担う
- **Python 部分 (pipeline/, utils/)**: `uv sync` で依存解決。`uv run python <script>` で実行
- フォーマット: `ruff format .`、リント: `ruff check .`（Python のみ）
- `config.yaml` にシークレットを書かない。`.env` に `DISCORD_TOKEN` を設定する
- フェーズ間の VRAM 解放は必須: `del model → gc.collect() → torch.cuda.empty_cache()`
- LLM の `n_ctx` は 16384 以上に設定しない

### Testing Requirements

- テストランナー: `pytest`（Python）
- `uv run pytest tests/` でテスト実行
- LLM を使うテストはモック必須（実モデルをロードしない）

### Common Patterns

- サブプロセス起動: `bot.js` が `uv run python pipeline/transcriber.py <sessionId>` を `spawn` する
- OOM 対応: ASR は large-v3 → medium → CPU の段階的フォールバック、LLM は exit code 2 で中断しチャンク要約を部分保存
- チャットログ収集: 録音開始時刻の Snowflake 以降のメッセージを Discord API から取得

---

## Dependencies

### Internal

- `utils/chunker.py` — `pipeline/summarizer.py` がインポートして使用
- `utils/memory.py` — モデルアンロードの共通ユーティリティ（pipeline 内でも同等処理を直接実装）

### External

| パッケージ | 用途 |
|---|---|
| `discord.js` + `@discordjs/voice` | Discord Bot + VC 録音 |
| `prism-media` | Opus → PCM デコード |
| `py-cord >= 2.6` | Python Discord 連携（現状は main.py スタブのみ） |
| `openai-whisper` | ASR（large-v3 / medium） |
| `llama-cpp-python` | LLM 推論（Gemma-4-26B GGUF） |
| `PyYAML` | config.yaml 読み込み |
| `python-dotenv` | .env 読み込み |

<!-- MANUAL: ボット固有のメモはここ以降に追記 -->
