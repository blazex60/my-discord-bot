# discord-minutes-bot

Discord VC の音声をローカル Linux 環境で完全オフライン処理し、Markdown 形式の議事録を自動生成するボット。

## ⚠️ DAVE 制限事項（重要）

> Discord が導入した DAVE (End-to-End Encryption) プロトコルにより、現在ボット経由での音声録音は動作しません。
> @discordjs/voice の Issue で進捗を追跡できます：
> https://github.com/discordjs/voice/issues/532

**このボットは現在、実装は完成していますが DAVE により実際の VC 音声受信ができません。**

---

## 概要

本ボットは以下の処理を自動化します：

1. **録音** — Node.js ボット（discord.js）が Discord VC に参加し、参加ユーザーの音声を PCM → WAV に変換
2. **音声認識（ASR）** — Whisper (OpenAI) で WAV → トランスクリプト生成
3. **LLM 要約** — llama-cpp-python で大規模言語モデルを使用し、議事録を Markdown 生成
4. **送信** — 議事録を Discord に投稿、一時ファイル削除

外部 AI API は一切使用せず、すべての処理をローカル GPU で実行します。

---

## 技術スタック

| 用途 | ライブラリ・モデル |
|---|---|
| **Discord クライアント** | Node.js 20+, discord.js v14, @discordjs/voice |
| **音声処理** | prism-media (Opus デコード) |
| **ASR（第1候補）** | openai-whisper medium |
| **ASR（フォールバック）** | openai-whisper base |
| **LLM 推論エンジン** | llama-cpp-python |
| **LLM モデル** | Qwen3.5-27B-Instruct (GGUF Q4_K_M 形式) |
| **設定管理** | PyYAML |
| **Python 環境管理** | uv |

### ハードウェア要件

| 項目 | 推奨スペック |
|---|---|
| **OS** | Linux (Arch Linux / Ubuntu 22.04 LTS) |
| **GPU** | NVIDIA GTX 980 Ti 以上 (VRAM 6GB+) |
| **GPU ドライバ** | NVIDIA Driver 535 系以降 |
| **CUDA** | 12.x |
| **RAM** | 32GB 以上 |

---

## セットアップ

### 1. リポジトリのクローンと依存関係のインストール

```bash
# Node.js 依存関係
npm install

# Python 依存関係（uv を使用）
uv sync
```

### 2. Discord Token の設定

```bash
# .env ファイルを作成
cp .env.example .env
```

`.env` ファイルに Discord Token を記載します：

```
DISCORD_TOKEN=your_discord_bot_token_here
```

**重要：** `.env` は `.gitignore` 対象です。環境変数で直接渡す場合は以下のようにします：

```bash
export DISCORD_TOKEN=your_token
node bot.js
```

### 3. LLM モデルの配置

Qwen3.5-27B-Instruct GGUF (Q4_K_M) をダウンロードして、`models/` ディレクトリに配置します：

```bash
mkdir -p models
# qwen3.5-27b.q4_k_m.gguf をここに配置
```

モデルは Hugging Face から取得できます。`config.yaml` の `llm.model_path` で指定されているパスに配置してください。

### 4. 起動

```bash
node bot.js
```

ログに以下のようなメッセージが表示されれば、正常に起動しています：

```
[Bot] ログイン完了: YourBot#1234
[Bot] スラッシュコマンド更新完了
```

---

## Discord コマンド

本ボットは以下の 3 つのスラッシュコマンドを提供します：

### `/record_start`

VC に参加して録音を開始します。

```
/record_start
```

**動作：**
- ボットがコマンド実行者の VC に参加
- 参加ユーザーの音声を受信開始
- ユーザーごとに別々の WAV ファイルに保存（`tmp/recordings/{sessionId}_{userId}.wav`）
- チャットメッセージも自動収集（`config.yaml` で `chat.enabled: true` の場合）

### `/record_stop`

録音を停止し、バッチ処理（ASR → LLM 要約）を開始します。

```
/record_stop
```

**動作：**
1. VC から切断
2. 保存した WAV ファイルをトランスクリプト化（Whisper）
3. トランスクリプトから議事録を生成（LLM）
4. Markdown ファイルをボットが投稿
5. 一時ファイル削除

### `/transcribe_only`

既存の WAV ファイルから ASR・要約のみ再実行します。

```
/transcribe_only <session_id>
```

**用途：** 録音失敗時やパラメータ調整後に、WAV は保持しつつ音声認識と要約を再実行する場合。

---

## パイプラインアーキテクチャ

```
┌─────────────────────────────────────────────────────────────┐
│ フェーズ 1: 録音 (bot.js)                                   │
├─────────────────────────────────────────────────────────────┤
│ • @discordjs/voice + receiver でユーザーごとの Opus 受信    │
│ • prism-media でデコード → PCM バッファ蓄積                 │
│ • writePcmToWav() で WAV に変換                             │
│ • ファイル: tmp/recordings/{sessionId}_{userId}.wav         │
│ • 最大録音時間: 3 時間（超過時は自動停止）                  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ フェーズ 2: 音声認識 (pipeline/transcriber.py)              │
├─────────────────────────────────────────────────────────────┤
│ • Whisper (medium) を CUDA で実行                          │
│ • VRAM 不足時は Whisper base へ自動フォールバック           │
│ • 出力: tmp/transcripts/{sessionId}_transcript.txt          │
│ • メタデータ: tmp/transcripts/{sessionId}_meta.json         │
│ • チャットログ: tmp/transcripts/{sessionId}_chat.txt        │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ フェーズ 3: LLM 要約 (pipeline/summarizer.py)               │
├─────────────────────────────────────────────────────────────┤
│ • llama-cpp-python で Qwen3.5-27B-Instruct を実行          │
│ • チャンク分割 (2200 tokens/chunk)                          │
│ • 2 段階要約:                                               │
│   1. 各チャンク → 要点抽出                                   │
│   2. 統合 → Markdown (概要/決定事項/ToDo)                   │
│ • VRAM 不足時は partial_*.txt を出力                        │
│ • 出力: output/minutes_{sessionId}.md                       │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ フェーズ 4: 送信と清掃 (bot.js)                             │
├─────────────────────────────────────────────────────────────┤
│ • output/minutes_{sessionId}.md を Discord に投稿           │
│ • tmp/recordings/{sessionId}_* を削除                       │
│ • tmp/transcripts/{sessionId}_* を削除                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 設定ファイル

### config.yaml

```yaml
discord:
  command_prefix: "/"

asr:
  primary_model: "whisper-medium"
  fallback_model: "whisper-base"
  device: "cuda"

llm:
  model_path: "models/qwen3.5-27b.q4_k_m.gguf"
  n_ctx: 4096
  n_gpu_layers: 20
  n_threads: 8
  chunk_size_tokens: 2200

storage:
  output_dir: "output/"
  tmp_dir: "tmp/"
  warn_threshold_gb: 20

chat:
  enabled: true

greenboost:
  enabled: false
```

**主要パラメータ：**

| パラメータ | 説明 |
|---|---|
| `asr.primary_model` | ASR の第 1 候補モデル |
| `asr.fallback_model` | VRAM 不足時の フォールバック モデル |
| `llm.model_path` | GGUF モデルのパス（相対パス） |
| `llm.n_ctx` | コンテキスト長（最大 4096 推奨） |
| `llm.n_gpu_layers` | GPU メモリに乗せるレイヤー数（VRAM に応じて調整） |
| `llm.chunk_size_tokens` | LLM 要約時のチャンク分割サイズ |
| `llm.n_threads` | CPU スレッド数 |
| `chat.enabled` | チャットログ自動収集（有効/無効） |

---

## エラーハンドリング

### ASR（音声認識）エラー

| エラー | 対応 |
|---|---|
| VRAM 不足（OOM） | Whisper medium → base へ自動フォールバック |
| その他エラー（終了コード 非 0） | バッチ処理中断、Discord へエラー通知 |

### LLM（要約）エラー

| エラー | 対応 |
|---|---|
| VRAM 不足（終了コード 2） | 生成済みチャンク要約を `partial_*.txt` として送信 |
| その他エラー | バッチ処理中断、Discord へエラー通知 |

### 録音エラー

| エラー | 対応 |
|---|---|
| VC 接続失敗 | Discord へエラー通知、WAV 破棄なし |
| 最大時間超過（3 時間） | 自動停止、バッチ処理へ自動移行 |
| Discord Token 期限切れ | メッセージを直接チャンネルに投稿 |

---

## ファイル構成

```
discord-minutes-bot/
├── bot.js                    # メインボット（Node.js）
├── package.json              # Node.js 依存関係
├── pyproject.toml            # Python 依存関係
├── config.yaml               # 設定ファイル
├── .env.example              # 環境変数テンプレート
│
├── pipeline/
│   ├── transcriber.py        # 音声認識（Whisper）
│   ├── summarizer.py         # LLM 要約
│   ├── chunker.py            # テキスト分割
│   └── memory.py             # VRAM 管理ユーティリティ
│
├── tmp/                      # 一時ファイル（自動削除）
│   ├── recordings/           # WAV ファイル
│   └── transcripts/          # トランスクリプト・メタデータ
│
├── output/                   # 最終出力（議事録 Markdown）
│   └── minutes_*.md
│
└── README.md                 # このファイル
```

---

## トラブルシューティング

### Discord に接続できない

```
エラー: DISCORD_TOKEN が設定されていません
```

**対応：** `.env` ファイルに正しい Discord Token を記載してください。

```bash
cat .env
# DISCORD_TOKEN=your_token_here
```

### Whisper が VRAM 不足で失敗

```
CUDA OutOfMemoryError
```

**対応：** config.yaml の `asr.fallback_model` が自動的に起動します。

それでもダメな場合、`n_gpu_layers` を減らして GPU メモリ使用量を削減してください。

### LLM が VRAM 不足で失敗

```
終了コード 2: LLM OOM
```

**対応：** 以下のいずれかを実施：
- `llm.n_gpu_layers` を減らす
- `llm.chunk_size_tokens` を減らす
- より小さいモデル（Qwen2.5-14B など）に変更

### wav ファイルが tmp/ に残る

**原因：** バッチ処理中にエラーが発生した可能性があります。

**対応：** 手動で削除するか、`/transcribe_only <session_id>` で再実行してください。

---

## 開発・カスタマイズ

### コード整形（Python）

```bash
uv run ruff format pipeline/
```

### リント チェック（Python）

```bash
uv run ruff check pipeline/
```

### テスト実行

```bash
uv run pytest tests/
```

### ログ出力確認

```bash
node bot.js 2>&1 | tee bot.log
```

---

## ライセンス

MIT

---

## 参考資料

- [discord.js 公式ドキュメント](https://discord.js.org/)
- [@discordjs/voice ドキュメント](https://discordjs.guide/voice/)
- [OpenAI Whisper GitHub](https://github.com/openai/whisper)
- [llama-cpp-python GitHub](https://github.com/abetlen/llama-cpp-python)
- [DAVE Issue (@discordjs/voice)](https://github.com/discordjs/voice/issues/532)
