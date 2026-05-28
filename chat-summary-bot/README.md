# Chat Summary Bot

Discord サーバーの会話を LLM で要約・検索・監視するボット。メッセージを SQLite に蓄積し、テキストマイニングやオンデマンド要約、定期自動要約に対応しています。

## 機能概要

- **オンデマンド要約** - 直近のメッセージを箇条書きで要約
- **キーワード検索** - テーマに関連する会話を検索・要約（リンク付き）
- **追いつき要約** - 特定のテーマの流れを時系列で説明
- **チャンネル監視管理** - メッセージ保存対象外チャンネルを指定
- **定期自動投稿** - cron 式で定期的にまとめを投稿

## コマンド一覧

### 要約・検索

| コマンド | 説明 | 例 |
|---------|------|-----|
| `/summary [count]` | 直近 N 件のメッセージを箇条書きで要約（デフォルト: 50）| `/summary 30` |
| `/search <query>` | キーワードに関連する会話を要約 + リンク（上位5件）| `/search Python` |
| `/catch_up <topic>` | 特定の話題の流れを時系列で要約 | `/catch_up イベント企画` |

### チャンネル監視管理

| コマンド | 説明 |
|---------|------|
| `/watch add <channel>` | チャンネルを監視除外リストに追加（メッセージ保存対象外）|
| `/watch remove <channel>` | チャンネルの監視除外を解除（メッセージ保存再開）|

### 定期自動投稿

| コマンド | 説明 | 例 |
|---------|------|-----|
| `/autopost set <cron> [channel]` | cron 式で定期投稿を設定 | `/autopost set "0 9 * * *"` （毎日 9 時）|
| `/autopost off` | 定期投稿を停止 | |

**cron 式の形式**: `分 時 日 月 曜`（5 項目スペース区切り）

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────┐
│ Discord Server                                          │
└──────────────┬──────────────────────────────────────────┘
               │ on_message (メッセージイベント)
               ▼
         ┌──────────────┐
         │  bot.py      │ ← slash commands (/summary, /search...)
         │ (discord.py) │
         └──────┬───────┘
                │
        ┌───────┴────────────────┬──────────────┬────────────┐
        │                        │              │            │
        ▼                        ▼              ▼            ▼
    ┌────────────┐          ┌─────────────┐ ┌────────────┐ ┌──────────────┐
    │ collector  │          │ db.py       │ │llm_client  │ │ scheduler.py │
    │ (fetch_*)  │          │ (Database)  │ │(LLMClient) │ │(AutoPost)    │
    └────────────┘          └──────┬──────┘ └─────┬──────┘ └──────────────┘
        │                          │              │
        │                          ▼              ▼
        │                    ┌───────────────────────────┐
        └───────────────────→│ SQLite (messages.db)      │
                             │ - TTL 管理 (30日)         │
                             │ - メッセージキャッシュ    │
                             │ - 設定永続化              │
                             └──────────┬────────────────┘
                                        │
                          ──────────────┴──────────────
                          │
                          ▼
                    ┌─────────────────────────┐
                    │ llama-cpp HTTP Server   │
                    │ (Gemma4 26B, CPU推論)   │
                    │ /completion endpoint    │
                    └─────────────────────────┘
```

## セットアップ

### 前提条件

- **OS**: Linux (Arch Linux / Ubuntu 22.04 LTS 等)
- **Python**: 3.12 以上
- **RAM**: 32GB 以上（Gemma4 26B CPU 推論）
- **Docker & Docker Compose**: 最新版

### インストール手順

#### 1. モデルの配置

[Gemma4 26B GGUF](https://huggingface.co/lmstudio-ai/gemma-2-27b-it-GGUF) をダウンロードし、`models/` ディレクトリに配置：

```bash
mkdir -p models
# gemma4-26b.gguf を models/ に配置
```

#### 2. 環境変数の設定

`.env` ファイルを作成：

```bash
cp .env.example .env
```

`.env` を編集して Discord トークンを設定：

```env
DISCORD_TOKEN=your_discord_token_here
LLM_URL=http://llm:8080
```

#### 3. Docker Compose で起動

```bash
docker compose up -d
```

ボットが起動し、LLM サーバーがヘルスチェック（最大 60 秒）の後に接続されます。

```bash
# ログ確認
docker compose logs -f bot
```

## ローカル開発

### 環境構築

```bash
# 依存関係をインストール
uv sync

# LLM サーバーを別ターミナルで起動
docker run --rm \
  -v $(pwd)/models:/models \
  -p 8080:8080 \
  ghcr.io/ggml-org/llama.cpp:server \
  -m /models/gemma4-26b.gguf \
  --port 8080 --host 0.0.0.0 \
  --ctx-size 8192 --n-gpu-layers 0
```

### ボット実行

```bash
# config.yaml の llm.url が http://localhost:8080 を指していることを確認
uv run python bot.py
```

### テスト実行

```bash
uv run pytest
```

## 設定

### config.yaml

```yaml
discord:
  command_prefix: "/"

llm:
  url: "http://llm:8080"           # LLM サーバー URL
  timeout_seconds: 120             # タイムアウト
  max_tokens: 2048                 # 最大生成トークン
  n_ctx: 8192                      # コンテキスト長

storage:
  db_path: "data/messages.db"      # SQLite データベースパス
  ttl_days: 30                     # メッセージの保持期間（日）
  max_messages_per_query: 80       # 1 回のクエリで取得可能な最大件数

monitoring:
  excluded_channels: []            # 監視除外チャンネル（初期値）

autopost:
  enabled: false
  default_channel: null
```

### 環境変数

- `DISCORD_TOKEN` (必須) - Discord ボット トークン
- `LLM_URL` (オプション) - LLM サーバー URL（`config.yaml` の値を上書き）

## 内部構造

### ファイル構成

```
chat-summary-bot/
├── bot.py              # メインエントリーポイント（slash commands）
├── collector.py        # メッセージ収集（DB + Discord API）
├── db.py               # SQLite ラッパー（TTL 管理付き）
├── llm_client.py       # llama-cpp HTTP クライアント
├── scheduler.py        # APScheduler による定期投稿管理
├── prompts.py          # LLM プロンプト定義
├── config.yaml         # ボット設定
├── pyproject.toml      # uv 依存関係定義
├── Dockerfile          # コンテナイメージ定義
├── docker-compose.yml  # ボット + LLM サービス定義
├── .env.example        # 環境変数テンプレート
└── tests/              # テストスイート
```

### データフロー

#### メッセージ保存（オンデマンド）

1. Discord サーバーでメッセージが投稿される
2. `on_message` イベントハンドラが発火
3. ボットメッセージ・除外チャンネルはスキップ
4. メッセージを SQLite に保存（TTL 30 日）

#### TTL クリーンアップ

- バックグラウンドタスク `_ttl_cleanup_task()` が 1 時間ごとに実行
- 期限切れメッセージを削除

#### 要約処理

1. `/summary` / `/search` / `/catch_up` コマンド実行
2. `collector.py` でメッセージを取得
   - `fetch_recent()`: DB 優先 → 不足分を Discord API で補完
   - `fetch_by_topic()`: DB の全文検索（LIKE 検索）
3. トークン上限を考慮してメッセージをトランケーション
4. `prompts.py` でプロンプトを構築
5. `llm_client.py` が llama-cpp HTTP サーバーに POST
6. 生成されたテキストを Discord に投稿

#### 定期自動投稿

1. `/autopost set <cron> [channel]` で設定
2. `scheduler.py` (APScheduler) が cron トリガーを登録
3. 設定は SQLite config テーブルに永続化
4. ボット起動時に DB から復元
5. スケジュール時刻に `_autopost_callback()` が実行
6. 要約を自動生成して投稿

### トークン管理

- **トークン数 = 文字数 ÷ 2** で概算（日本語対応）
- メッセージは新しい順で取得し、古い順で並べ替え
- 合計トークン数が LLM のコンテキスト長 - 3000 を超えるとトランケーション
- トランケーション発生時は `※古いメッセージは省略しました` を付記

## 技術スタック

| 項目 | 採用技術 |
|------|---------|
| Python | 3.12 |
| Discord ライブラリ | py-cord ≥2.6 |
| 非同期処理 | asyncio |
| LLM 推論 | llama-cpp (HTTP サーバー) |
| メッセージモデル | Gemma4 26B (GGUF) |
| データベース | SQLite (aiosqlite) |
| スケジューリング | APScheduler |
| HTTP クライアント | httpx |
| パッケージ管理 | uv |

## トラブルシューティング

### LLM サーバーに接続できない

```
LLMUnavailableError: LLM サーバーに接続できません
```

**原因と対策:**
- `LLM_URL` が正しく設定されているか確認
- Docker Compose で LLM コンテナが起動しているか確認: `docker compose ps`
- ヘルスチェック状態を確認: `curl http://localhost:8080/health`

### LLM がタイムアウトしている

```
LLMUnavailableError: LLM サーバーがタイムアウトしました
```

**原因と対策:**
- `config.yaml` の `llm.timeout_seconds` を増やす（例: 180）
- RAM 不足で推論が遅い場合、GPU レイヤーの設定を検討

### メモリ不足エラー

**原因と対策:**
- Gemma4 26B は 32GB RAM を前提
- 小さなモデル (7B～13B) への変更を検討
- `docker-compose.yml` の `--n-gpu-layers` を 32 以上に設定して GPU を活用

### データベースがロックされている

```
sqlite3.OperationalError: database is locked
```

**対策:**
- 複数のプロセスが同時にアクセスしていないか確認
- `config.yaml` の `db_path` が一意か確認

## ログ確認

```bash
# Docker Compose ログ
docker compose logs -f bot

# ローカル実行時
uv run python bot.py  # コンソールに出力
```

## ライセンス

このプロジェクトの詳細は各ボットの CLAUDE.md を参照してください。
