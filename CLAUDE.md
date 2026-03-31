# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

Discord VC の音声をローカルLinux環境で完全オフライン処理し、Markdown形式の議事録を自動生成するBot。
外部AI APIは一切使用しない。夜間バッチ処理を前提とし、速度より**安定性・精度を最優先**とする。

---

## 環境

| 項目 | 内容 |
|---|---|
| OS | Linux (Arch Linux / Ubuntu 22.04 LTS) |
| Python | 3.12 |
| GPU | NVIDIA GTX 980 Ti (VRAM 6GB) / CUDA 12.x |
| RAM | 32GB |
| NVIDIA Driver | 535系以降 |

---

## セットアップ

**パッケージ管理: uv**

```bash
uv sync          # 依存関係インストール・仮想環境構築
uv add <pkg>     # パッケージ追加
```

**必須環境変数 — config.yaml には絶対に書かない**

```bash
cp .env.example .env
# .env を編集して DISCORD_TOKEN を設定する
```

`.env` は `.gitignore` 対象。環境変数で直接渡す場合は `export DISCORD_TOKEN=...` でも動作する。

**フォーマッター: ruff**

```bash
ruff format .    # フォーマット
ruff check .     # リント
```

---

## 技術スタック

| 用途 | ライブラリ・モデル |
|---|---|
| Discord Bot | `py-cord >= 2.6` (Voice Receive対応版) |
| ASR (第1候補) | `openai-whisper` large-v3 |
| ASR (フォールバック) | `openai-whisper` medium |
| LLM推論エンジン | `llama-cpp-python` |
| LLMモデル | Qwen2.5-14B-Instruct または Llama-3.1-14B-Instruct (GGUF Q4_K_M) |
| メモリ管理 | `gc`, `torch.cuda.empty_cache()` |
| 設定管理 | `config.yaml` (PyYAML) |

---

## パイプライン設計（完全直列・メモリ排他制御）

各フェーズは **独立したサブプロセス** (`subprocess.run()`) として実行し、
フェーズ終了時に必ず `del model → gc.collect() → torch.cuda.empty_cache()` を実行する。

```
[フェーズ1] 録音 (bot.py / recorder.py)
  Discord VC → WaveSink → tmp/recordings/{timestamp}_{user_id}.wav

[フェーズ2] ASR (transcriber.py をサブプロセスで起動)
  Whisper large-v3 ロード → WAVファイルを順次処理 → トランスクリプト生成
  → Whisper アンロード + gc.collect() + cuda.empty_cache()

[フェーズ3] LLM要約 (summarizer.py をサブプロセスで起動)
  llama.cpp ロード → チャンク分割 → 2段階要約 → Markdown生成
  → LLM アンロード + gc.collect() + cuda.empty_cache()

[フェーズ4] 出力 (bot.py)
  output/minutes_{timestamp}.md 保存 → discord.File で送信
  → tmp/ 以下の一時ファイル削除
```

---

## 実装ルール

### recorder.py

- `py-cord` の `WaveSink` を使用し、ユーザーIDごとに独立したWAVファイルを保存する。
- ファイル命名: `tmp/recordings/{YYYYMMDD_HHMMSS}_{user_id}.wav`
- 録音最大時間: **3時間**。超過時は自動停止してバッチ処理へ移行し、Discordへ通知する。
- 録音中に接続が切断された場合、保存済みWAVを破棄せず保持してエラーを通知する。

### transcriber.py

- `device="cuda"` でWhisper large-v3をロードする。
- `torch.cuda.OutOfMemoryError` が発生した場合、自動的に `medium` モデルへフォールバックして再試行する。
- 出力トランスクリプト形式:
  ```
  [YYYY-MM-DD HH:MM:SS] ユーザー名: 発言内容
  ```
- 処理完了後、必ずモデルをアンロードしてVRAMを解放する。

### chunker.py

- `llama-cpp-python` の `llm.tokenize()` を使用して正確なトークン数を計算する。
- チャンクの最大サイズ: **2200トークン**（config.yaml で設定可能）。
- テキストをトークン数ベースで分割し、チャンクリストとして返す。

### summarizer.py

- `llama-cpp-python` の `Llama` クラスを以下の設定でロードする:
  ```python
  llm = Llama(
      model_path=config["llm"]["model_path"],
      n_ctx=4096,        # デフォルト。最大8192まで許容。16384以上は禁止。
      n_gpu_layers=20,   # VRAMに収まる範囲で調整（nvidia-smiで確認）
      n_threads=8,
      verbose=False,
  )
  ```
- **2段階要約パイプライン**を実装する:
  1. **Step 1 (チャンク要約):** 各チャンクに対して要点を生成する。
  2. **Step 2 (統合要約):** Step 1の全チャンク要約を結合し、以下の構成でMarkdownを生成する:
     - `## 会議の概要`
     - `## 決定事項`
     - `## ToDo`
- 推論タイムアウトは設定しない（夜間バッチ前提）。

### memory.py

```python
import gc
import torch

def unload_model(model):
    """モデルを安全にアンロードしてVRAMとRAMを解放する"""
    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
```

---

## Discord コマンド一覧

| コマンド | 動作 |
|---|---|
| `/record_start` | VCに参加して録音を開始する |
| `/record_stop` | 録音を停止してバッチ処理を開始する |
| `/transcribe_only` | 既存のWAVファイルからASR・要約のみ再実行する（録音失敗時の再開用） |

---

## 進捗通知（Discordメッセージ編集）

処理中はDiscordのメッセージを `message.edit()` でリアルタイム更新する。

| フェーズ | メッセージ |
|---|---|
| 録音中 | 🔴 録音中... |
| バッチ開始 | ⏳ バッチ処理を開始しました... |
| ASR処理中 | 🎤 音声認識処理中 (Whisper)... `{n}/{total}` ファイル |
| LLM処理中 | 🧠 議事録生成中 (LLM)... チャンク `{n}/{total}` を処理中 |
| 完了 | ✅ 議事録を生成しました（所要時間: `{elapsed}` 分） |
| エラー | ❌ エラーが発生しました: `{エラー種別}` |

---

## エラーハンドリング

| エラー種別 | 対応 |
|---|---|
| OOM (ASR) | Whisper medium へ自動フォールバックして再試行 |
| OOM (LLM) | 処理中断・生成済みチャンク要約を `.txt` として保存して送信 |
| 録音失敗 | WAVファイルを保持してエラー通知。`/transcribe_only` で再開可能 |
| ストレージ不足 | 処理中断・WAVを削除して再試行するかDiscordで確認 |
| 録音3時間超過 | 自動停止してバッチ処理へ移行 |

---

## config.yaml

```yaml
discord:
  command_prefix: "/"

asr:
  primary_model: "whisper-large-v3"
  fallback_model: "whisper-medium"
  device: "cuda"

llm:
  model_path: "models/qwen2.5-14b-instruct-q4_k_m.gguf"
  n_ctx: 4096
  n_gpu_layers: 20
  n_threads: 8
  chunk_size_tokens: 2200

storage:
  output_dir: "output/"
  tmp_dir: "tmp/"
  warn_threshold_gb: 20
  max_recording_hours: 3

greenboost:
  enabled: false
```

---

## GreenBoost（オプション）

VRAMをシステムRAM/NVMeで仮想拡張するNVIDIAのオープンソースドライバー。
**14B Q4_K_MモデルでVRAMが不足する場合のみ**検討する。デフォルト無効。

> GTX 980 Ti は PCIe 3.0 接続のため、GreenBoost有効時は推論速度が大幅に低下する可能性がある。

---

## 禁止事項

- 外部AI APIの使用（OpenAI API、Anthropic API 等）
- コンテキスト長 `n_ctx 16384` 以上の設定
- LLMに 30B クラス以上のモデルを使用すること（安定動作の保証なし）
- 録音完了後に `tmp/` 以外の場所へWAVを保存すること
- 議事録Markdown（`output/`）の自動削除
- `DISCORD_TOKEN` を config.yaml またはソースコードにハードコードすること
