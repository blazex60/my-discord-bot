# chat-summary-bot

カオスな雑談 Discord サーバー向けチャット要約 Bot。テキストチャンネルのメッセージを SQLite にキャッシュし、ローカル LLM（Gemma4 26B）で要約・検索・追いつきサポートを提供する。

## 機能

| コマンド | 動作 |
|---|---|
| `/summary [count]` | 直近 N 件のメッセージを箇条書きで要約（デフォルト 50） |
| `/search <query>` | キーワードに関連する会話を要約 + Discord リンク付きで返す |
| `/catch_up <topic>` | 特定話題の流れを時系列で追いつき要約する |
| `/watch add <channel>` | チャンネルを監視除外リストに追加 |
| `/watch remove <channel>` | チャンネルを監視再開 |
| `/autopost set <cron>` | cron 式で定期要約投稿を設定（例: `0 9 * * *`） |
| `/autopost off` | 定期投稿を停止 |

## アーキテクチャ

```
Discord VC
    │  on_message（全チャンネル・除外リスト以外）
    ▼
┌─────────────────────────────────────────────┐
│                  bot.py                     │
│  /summary  /search  /catch_up               │
│  /watch    /autopost                        │
└──────┬──────────────┬──────────────┬────────┘
       │              │              │
  collector.py   scheduler.py   prompts.py
  （DB優先取得）  （定期投稿）   （プロンプト）
       │
  ┌────┴────┐
  │  db.py  │  SQLite + TTL 自動削除
  └────┬────┘
       │ HTTP
  llm_client.py
       │
  llama-cpp-python（Gemma4 26B, CPU実行）
```

### Docker Compose 構成

```
bot サービス（Python）
  └─ depends_on: llm（healthcheck 待機）

llm サービス（ghcr.io/ggerganov/llama.cpp:server）
  └─ Gemma4 26B GGUF, --n-gpu-layers 0（CPU全処理）
```

## 動作環境

| 項目 | 内容 |
|---|---|
| OS | Linux |
| RAM | 32GB 以上推奨（Gemma4 26B CPU 推論のため） |
| Python | 3.12 |
| Discord ライブラリ | py-cord 2.7 |

## セットアップ

### 1. モデルの配置

Gemma4 26B の GGUF ファイルを `models/` に配置する。

```bash
# 例: gemma-4-26b-it-Q4_K_M.gguf を models/ に配置
```

### 2. 環境変数の設定

```bash
cp .env.example .env
# .env を編集して DISCORD_TOKEN を設定する
```

### 3. 起動

```bash
docker compose up -d
```

LLM サービスのモデルロードが完了してから Bot が起動する（healthcheck により自動待機）。

## ローカル開発

```bash
uv sync
uv run python bot.py
```

LLM は別途 `config.yaml` の `llm.url` で指定したサーバーが起動している必要がある。

## 設定

`config.yaml` で動作を調整できる（`DISCORD_TOKEN` は `.env` で管理する）。

```yaml
llm:
  url: "http://llm:8080"
  timeout_seconds: 120
  max_tokens: 2048
  n_ctx: 8192

storage:
  db_path: "data/messages.db"
  ttl_days: 30              # メッセージの保持期間
  max_messages_per_query: 80
```

## 開発

```bash
# テスト
uv run pytest tests/

# フォーマット / リント
uv run ruff format .
uv run ruff check .
```

## ライセンス

MIT
