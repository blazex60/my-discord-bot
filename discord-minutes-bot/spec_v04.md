# Discord VC 議事録自動作成ボット 仕様書 (v0.4)

**〜 RAM 32GB / GTX 980 Ti・Linux・夜間バッチ・安定性最優先モデル 〜**

---

## 1. プロジェクト概要

外部APIを一切使用せず、ローカルLinuxサーバーのリソースのみで Discord VC の音声を議事録化するシステム。
**速度よりも安定性・精度を最優先**し、夜間バッチ処理として完全オフラインで動作させることを前提とする。
メモリ管理・コンテキスト長制御・エラーハンドリングを設計の中心に置く。

---

## 2. 動作環境・制約事項

| 項目 | 内容 |
|---|---|
| OS | Linux (Ubuntu 22.04 LTS 推奨) |
| CPU | Intel Core i7 (8th Gen) |
| GPU | NVIDIA GeForce GTX 980 Ti (VRAM 6GB, GDDR5) |
| RAM | 32GB |
| Storage | 512GB SSD |
| ネットワーク | 外部AI APIへの通信不可（完全オフライン推論） |
| GreenBoost | オプション導入可（§5 参照） |

### 2.1. ドライバ・ランタイム要件

- NVIDIA ドライバ: `535` 系以降推奨（CUDA 12.x 対応）
- CUDA Toolkit: `12.x`
- Python: `3.11` 以降
- 仮想環境: `venv` または `conda` による環境分離を必須とする

---

## 3. システムアーキテクチャ（完全直列パイプライン）

RAM 32GB および VRAM 6GB の制約下で ASR モデルと LLM を安全に動作させるため、
**各フェーズを完全に直列化し、フェーズ移行時に必ずメモリ・VRAMを明示的解放する**。

```
[フェーズ1: 録音]
Discord VC音声受信 → WAV保存 (話者別)
↓ (録音終了後・Bot切断後)
[フェーズ2: 音声認識 (ASR)]
ASRモデルロード → 文字起こし → ASRモデルアンロード + gc.collect()
↓
[フェーズ3: 議事録生成 (LLM)]
LLMロード → チャンク分割要約 → 最終Markdown生成 → LLMアンロード + gc.collect()
↓
[フェーズ4: 出力・クリーンアップ]
Markdownファイル保存 → Discordへ送信 → 中間ファイル削除
```

### 3.1. メモリ解放の実装方針

- モデルのアンロードは `del model` + `gc.collect()` + `torch.cuda.empty_cache()` を必ずセットで実行する。
- 各フェーズは**独立した Python サブプロセス**（`subprocess.run()`）として起動することを推奨する。
  これにより、フェーズ失敗時のメモリリークをプロセス終了によって確実に回収できる。

---

## 4. 機能要件

### 4.1. 録音機能 (Discord連携)

- **使用ライブラリ:** `py-cord` (Voice Receive 対応版、`2.6.x` 以降)
- **録音コマンド:**

  | コマンド | 動作 |
  |---|---|
  | `/record_start` | VC に Bot が参加し、録音を開始する |
  | `/record_stop` | 録音を停止し、Bot が VC から切断する。以降バッチ処理へ移行 |

- **話者分離:**
  - `WaveSink` を使用し、DiscordユーザーIDごとに独立したWAVファイルを生成する。
  - ファイル命名規則: `{timestamp}_{user_id}.wav`

- **音声フォーマット:** WAV（ロスレス・一時保存用）

- **制限:**
  - 映像（画面共有・カメラ）は処理対象外とする。
  - 1回の録音セッションの最大時間は **3時間** とし、超過時は自動で停止・通知する。

- **注意事項:**
  - `py-cord` の Voice Receive は非同期I/Oに依存するため、録音中は Discord イベントループへの負荷に注意する。
  - 録音失敗（接続切断等）時は、保存済みの音声データを破棄せず保持し、Discord へエラー通知する。

### 4.2. 音声認識・文字起こし機能 (ASR)

- **使用モデル候補（優先順）:**

  | 優先度 | モデル | VRAM 目安 | 特記 |
  |---|---|---|---|
  | 第1候補 | Whisper large-v3 (openai) | ~2.5GB | 日本語精度が高く安定 |
  | 第2候補 | Whisper medium | ~1.5GB | メモリ不足時のフォールバック |
  | 参考 | Kimi-Audio | 要検証 | 汎用音声基盤モデル・動作確認後に採用判断 |

  > ⚠️ Kimi-Audio は大規模な音声基盤モデルであり、本環境での安定動作は事前の検証を要する。
  > 検証完了まではWhisperシリーズを主系統として採用する。

- **処理ロジック:**
  1. フェーズ2 開始時、ASRモデルをロードする（GPU利用: `device="cuda"`）。
  2. 話者ごとのWAVファイルを**順次（直列）**処理し、テキスト化する。
  3. 各発話にDiscordユーザーIDとタイムスタンプを付与し、以下の形式で結合する:

     ```
     [YYYY-MM-DD HH:MM:SS] ユーザー名: 発言内容
     ```

  4. 処理完了後、モデルを完全にアンロードし、VRAMを解放する。

- **フォールバック:** `torch.cuda.OutOfMemoryError` 発生時は、自動的に `medium` モデルへ切り替えて再試行する。

### 4.3. 議事録作成機能 (LLM)

#### 4.3.1. モデル選定

- **推奨モデル:** `Qwen2.5-14B-Instruct` または `Llama-3.1-14B-Instruct` の GGUF 形式
- **量子化:** `Q4_K_M`（精度と容量のバランスが良く、14B クラスでも32GB RAM 内に収まる）
- **推論エンジン:** `llama.cpp` + Pythonバインディング `llama-cpp-python`

  > 14B Q4_K_M はおよそ 8〜9GB のモデルサイズとなり、32GB RAM の制約内で安全に運用できる。
  > 30Bクラスは本環境では安定動作の保証が難しいため、採用しない。

- **GreenBoost の活用（オプション）:** § 5 参照。

#### 4.3.2. コンテキスト長の制御

本システムの最重要課題のひとつとして、コンテキスト超過によるクラッシュ・出力異常を防ぐため、以下のルールを設ける。

- **デフォルトコンテキスト長:** `-c 4096`
- **最大コンテキスト長:** `-c 8192`（6GB VRAM 環境下でのKVキャッシュの限界を考慮）
- `-c 16384` 以上は**使用禁止**とする。

#### 4.3.3. チャンク分割による2段階要約パイプライン

長時間会議のトランスクリプトがコンテキスト上限を超えることを前提に、以下の2段階処理を必須とする。

```
[Step 1] チャンク要約
トランスクリプトを 2000〜2500 トークン単位のチャンクに分割
→ 各チャンクに対して「要点・発言の概要」を生成

[Step 2] 統合要約
Step 1 の全チャンク要約を結合し、最終的な議事録 Markdown を1回の推論で生成
出力項目: 「## 会議の概要」「## 決定事項」「## ToDo」
```

- チャンク分割はトークナイザー（`llama-cpp-python` の `tokenize()`）を使用し、正確なトークン数ベースで行う。

#### 4.3.4. LLM ロード設定

```python
llm = Llama(
    model_path="/path/to/model.gguf",
    n_ctx=4096,           # デフォルトコンテキスト長
    n_gpu_layers=20,      # VRAM 6GB に収まる範囲でオフロード（要チューニング）
    n_threads=8,          # CPU スレッド数（i7 8th Gen 8コア想定）
    verbose=False,
)
```

- `n_gpu_layers` は VRAM 使用量を監視しながら調整する（`nvidia-smi` で確認）。
- 推論タイムアウトは設定しない（夜間バッチ前提のため）。

### 4.4. 出力・クリーンアップ機能

- **出力ファイル:** `minutes_{YYYY-MM-DD_HHMMSS}.md` として `/output/` ディレクトリへ保存
- **Discord 送信:** `discord.File` を使用して、コマンド実行元のテキストチャンネルへ送信
- **中間ファイルの削除:**
  - 送信完了後、以下のファイルを自動削除する:
    - フェーズ1 で生成した WAV ファイル（`/tmp/recordings/`）
    - フェーズ2 で生成したトランスクリプトテキスト（`/tmp/transcripts/`）
  - 議事録 Markdown（`/output/`）は**削除しない**。
- **ストレージ警告:** SSD 残容量が 20GB 未満になった場合、Discord へ警告通知する。

---

## 5. GreenBoost オプション

### 5.1. GreenBoost とは

NVIDIA GPU の VRAM を、システム RAM または NVMe SSD で仮想的に拡張するオープンソースドライバー。
6GB VRAM の制約を超えてより大きなモデルを動かすための**補助手段**として使用する。

### 5.2. 本システムでの位置づけ

- GreenBoost は**VRAM 不足を回避するための選択肢**であり、デフォルトでは無効とする。
- GreenBoost 有効時、モデルの超過分が RAM または NVMe 経由でアクセスされるため、**推論速度は低下する**。
  夜間バッチ処理のため、速度の低下は許容する。
- 導入を検討するケース: 14B Q4_K_M では精度不足と判断し、より大きなモデルを試したい場合のみ。

### 5.3. 導入手順（概要）

```bash
# GreenBoost カーネルモジュールのビルド・インストール
git clone https://github.com/nvidia/greenboost
cd greenboost
make && sudo make install

# NVMe スワップ領域の設定（推奨: 最低 16GB）
sudo fallocate -l 16G /swapfile_llm
sudo chmod 600 /swapfile_llm
sudo mkswap /swapfile_llm
sudo swapon /swapfile_llm
```

> ⚠️ GTX 980 Ti は PCIe 3.0 接続であり、帯域幅の制約から速度低下は顕著になる場合がある。
> 14B モデルで必要十分な精度が得られる場合は、GreenBoost の使用を推奨しない。

---

## 6. 非機能要件・UI/UX

### 6.1. 進捗の可視化

処理の各フェーズに合わせて、Discord のテキストチャンネル上のメッセージをリアルタイムで編集・更新する。

| フェーズ | Discord 表示メッセージ |
|---|---|
| 録音中 | 🔴 録音中... |
| 録音停止・バッチ開始 | ⏳ バッチ処理を開始しました... |
| ASR処理中 | 🎤 音声認識処理中 (Whisper)... `{n}/{total}` ファイル |
| LLM処理中 | 🧠 議事録生成中 (LLM)... チャンク `{n}/{total}` を処理中 |
| 送信・完了 | ✅ 議事録を生成しました（所要時間: `{elapsed}` 分） |
| エラー発生 | ❌ エラーが発生しました: `{エラー種別}` |

### 6.2. エラーハンドリング

| エラー種別 | 対応 |
|---|---|
| OOM (ASR) | 軽量モデル（Whisper medium）へ自動フォールバックし再試行 |
| OOM (LLM) | 処理を中断し、生成済みのチャンク要約を `.txt` として保存・送信 |
| 録音失敗 | WAVファイルを保持したままエラー通知。手動で `/transcribe_only` コマンドから再開できる |
| ストレージ不足 | 処理を中断し、WAVファイルを削除後に再試行するか否かをDiscordで確認 |
| タイムアウト（録音3時間超過） | 自動で録音停止し、バッチ処理へ移行 |

### 6.3. ログ

- すべてのフェーズの開始・終了・エラーを `/logs/bot_{date}.log` に記録する。
- ログは30日間保持し、自動削除する（`logrotate` で管理）。

---

## 7. ディレクトリ構成

```
/discord-minutes-bot/
├── bot.py               # Discord Botメイン
├── pipeline/
│   ├── recorder.py      # フェーズ1: 録音
│   ├── transcriber.py   # フェーズ2: ASR
│   └── summarizer.py    # フェーズ3: LLM要約
├── utils/
│   ├── chunker.py       # トークン分割ユーティリティ
│   └── memory.py        # メモリ解放ユーティリティ
├── output/              # 最終議事録の保存先
├── logs/                # ログ
├── tmp/
│   ├── recordings/      # WAV（一時）
│   └── transcripts/     # テキスト（一時）
├── models/              # GGUFモデルファイル
├── requirements.txt
└── config.yaml          # モデルパス・コンテキスト長等の設定
```

---

## 8. 設定ファイル例 (config.yaml)

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
  chunk_size_tokens: 2200  # チャンク分割の最大トークン数

storage:
  output_dir: "output/"
  tmp_dir: "tmp/"
  warn_threshold_gb: 20

greenboost:
  enabled: false  # 通常はfalse。VRAMが不足する場合のみtrueに変更
```

---

## 9. 開発優先順位・実装ロードマップ

| フェーズ | 内容 | 優先度 |
|---|---|---|
| Step 1 | 録音機能（py-cord + WaveSink）の動作確認 | 最高 |
| Step 2 | Whisper large-v3 による文字起こし単体テスト | 最高 |
| Step 3 | llama-cpp-python + 14B GGUF による要約テスト | 高 |
| Step 4 | チャンク分割ロジックの実装・検証 | 高 |
| Step 5 | フルパイプライン統合テスト（短時間会議で確認） | 高 |
| Step 6 | Discord Bot との結合・進捗表示の実装 | 中 |
| Step 7 | エラーハンドリング・ログ機能の実装 | 中 |
| Step 8 | Kimi-Audio の動作検証・採用判断 | 低 |
| Step 9 | GreenBoost の導入検討（必要な場合のみ） | 低 |
