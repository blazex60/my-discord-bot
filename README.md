# Discord VC 議事録自動作成ボット

> ⚠️ **重要な制限事項**: Discord が導入した DAVE (End-to-End Encryption) プロトコルにより、**現在 Bot 経由での音声録音は動作しません**。詳細は [DAVE_LIMITATION.md](./DAVE_LIMITATION.md) を参照してください。py-cord の [Issue #3139](https://github.com/Pycord-Development/pycord/issues/3139) で進捗を追跡できます。

Discord VC の音声をローカル Linux 環境で完全オフライン処理し、Markdown 形式の議事録を自動生成する Bot。
外部 AI API は一切使用しない。夜間バッチ処理を前提とし、速度より**安定性・精度を最優先**とする。

## 動作環境

| 項目 | 内容 |
|---|---|
| OS | Linux (Arch Linux / Ubuntu 22.04 LTS) |
| Python | 3.12 |
| GPU | NVIDIA GTX 980 Ti (VRAM 6GB) / CUDA 12.x |
| RAM | 32GB |
| NVIDIA Driver | 535 系以降 |

## セットアップ

### 1. 依存関係のインストール

```bash
uv sync
```

### 2. Discord Bot の設定

1. [Discord Developer Portal](https://discord.com/developers/applications) でアプリケーションを作成
2. **Bot** タブで以下の **Privileged Gateway Intents** を **すべて有効化**:
   - ✅ **PRESENCE INTENT**
   - ✅ **SERVER MEMBERS INTENT**
   - ✅ **MESSAGE CONTENT INTENT**
3. **OAuth2 → URL Generator** で以下を選択:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Connect`, `Speak`, `Use Voice Activity`
4. 生成された URL でサーバーに招待

### 3. 環境変数の設定

```bash
cp .env.example .env
# .env を編集して DISCORD_TOKEN を設定する
```

### 4. LLM モデルの配置

Qwen2.5-14B-Instruct または Llama-3.1-14B-Instruct の GGUF Q4_K_M ファイルを `models/` に配置する。

```bash
# 例: Hugging Face からダウンロード
# models/qwen2.5-14b-instruct-q4_k_m.gguf
```

> `config.yaml` の `llm.model_path` でパスを変更できる。

### 5. Bot の起動

```bash
uv run python bot.py
```

## 使い方

| コマンド | 動作 |
|---|---|
| `/record_start` | VC に参加して録音を開始する |
| `/record_stop` | 録音を停止してバッチ処理（ASR → 要約）を開始する |
| `/transcribe_only` | 既存の WAV ファイルから ASR・要約のみ再実行する（録音失敗時の再開用） |

処理の進捗は Discord のメッセージがリアルタイムで更新される。
完了後、議事録 Markdown ファイルが Discord に送信される。

## パイプライン

```
[フェーズ1] 録音 — Discord VC → WaveSink → tmp/recordings/{session_id}_{user_id}.wav
[フェーズ2] ASR  — Whisper large-v3 → tmp/transcripts/{session_id}_transcript.txt
[フェーズ3] 要約 — llama.cpp 2段階要約 → output/minutes_{session_id}.md
[フェーズ4] 送信 — discord.File で送信 → tmp/ 以下を削除
```

各フェーズは独立したサブプロセスとして実行される。フェーズ終了時に必ずモデルをアンロードして VRAM を解放する。

### 議事録の構成

```markdown
## 会議の概要
## 決定事項
## ToDo
```

## 設定

`config.yaml` で動作を調整できる（`DISCORD_TOKEN` は `.env` で管理し、ここには書かない）。

```yaml
llm:
  model_path: "models/qwen2.5-14b-instruct-q4_k_m.gguf"
  n_ctx: 4096        # 最大 8192。16384 以上は禁止。
  n_gpu_layers: 20   # VRAM に収まる範囲で調整
  chunk_size_tokens: 2200

storage:
  max_recording_hours: 3
```

## 開発

```bash
# テスト
uv run pytest

# フォーマット / リント
uv run ruff format .
uv run ruff check .
```

pre-commit フックが設定済みのため、`git commit` 時に自動でフォーマット・リントが実行される。

## エラーハンドリング

| エラー | 対応 |
|---|---|
| ASR OOM | Whisper medium へ自動フォールバック |
| LLM OOM | 生成済みチャンク要約を `.txt` で送信 |
| 録音失敗 | WAV を保持して通知。`/transcribe_only` で再開可能 |
| 録音 3 時間超過 | 自動停止してバッチ処理へ移行 |

## ライセンス

MIT
