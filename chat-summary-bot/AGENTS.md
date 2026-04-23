<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-22 | Updated: 2026-04-23 -->
<!-- Spec: ../.omc/specs/deep-interview-chat-summary-bot.md -->

# chat-summary-bot

## Purpose

カオスな雑談Discordサーバーのテキストチャンネルを対象に、会話を探しやすくし、
離席中の話題に短時間で追いつけるようにするBot。VC（音声チャンネル）は非対応。

discord-minutes-botとは完全に独立した設計。コードの共用なし。

---

## Key Files

| File | Description |
|------|-------------|
| `bot.py` | Discord Bot エントリーポイント・コマンド定義・on_message ハンドラ |
| `collector.py` | DB および Discord API からのメッセージ取得ロジック（`CollectResult` / トランケーション） |
| `llm_client.py` | llama-cpp-python HTTP サーバーへの非同期リクエストラッパー（`LLMClient` / `LLMUnavailableError`） |
| `db.py` | SQLite 操作・TTL 管理・メッセージ保存/削除（`Database` クラス） |
| `prompts.py` | LLM プロンプト組み立て関数（`build_summary_prompt` / `build_search_prompt` / `build_catchup_prompt`） |
| `scheduler.py` | 定期自動投稿のスケジュール管理（`AutoPostScheduler`） |
| `config.yaml` | TTL・LLM URL・n_ctx・監視設定など |
| `.env.example` | DISCORD_TOKEN 等のシークレットテンプレート |
| `pyproject.toml` | Python 依存関係（uv 管理） |
| `docker-compose.yml` | Bot サービスと LLM サーバーの 2 サービス構成 |
| `Dockerfile` | Bot コンテナのビルド定義 |

---

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `model/` | Gemma4 26B GGUF モデルファイル置き場（.gitignore 対象） |
| `tests/` | ユニット・統合テスト（see `tests/AGENTS.md`） |

---

## Architecture

### システム全体

```
[Discord テキストチャンネル（全チャンネル＋除外リスト設定）]
       ↓ on_message（リアルタイム受信）
[bot.py]
  ├─ messages テーブルへ保存（SQLite + TTL）
  └─ コマンド受信時
       ↓
[collector.py]  ── DB / Discord channel.history() からメッセージ取得
       ↓
[llm_client.py]  ── HTTP POST → llama-cpp-python サーバー
       ↓
[Gemma4 26B（Dockerサービス）]
  ※ チャンク分割なし。全テキストをそのままコンテキストへ
       ↓
[bot.py]  ── Discord へ返信
```

### Docker Compose 構成（2サービス）

```
docker-compose.yml
├── bot      ← Python Discord Bot
│   └── depends_on: llm (healthcheck 待機)
└── llm      ← llama-cpp-python HTTP サーバー (Gemma4 26B)
    └── volumes: ./models:/models
```

### SQLite スキーマ

```sql
-- メッセージキャッシュ（TTL付き）
CREATE TABLE messages (
  id          TEXT PRIMARY KEY,   -- Discord message ID
  channel_id  TEXT NOT NULL,
  author_name TEXT NOT NULL,
  content     TEXT NOT NULL,
  created_at  INTEGER NOT NULL,   -- Unix timestamp
  expires_at  INTEGER NOT NULL    -- TTL: Unix timestamp
);

-- Bot設定（除外チャンネル・自動投稿スケジュール等）
CREATE TABLE config (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
```

---

## Discord コマンド一覧

| コマンド | 動作 |
|---|---|
| `/summary [件数]` | 直近N件のメッセージを箇条書きで要約して返す |
| `/search [キーワード]` | 関連会話の要約文＋各メッセージへのDiscordリンクを返す |
| `/catch_up [話題]` | 指定した話題の流れを箇条書きで追いつき要約して返す |
| `/watch add #channel` | 監視除外リストからチャンネルを除外指定する |
| `/watch remove #channel` | 除外リストからチャンネルを外す（監視再開） |
| `/autopost set [cron]` | 定期自動投稿スケジュールを設定する（デフォルト無効） |
| `/autopost off` | 定期自動投稿を停止する |

---

## 出力形式

| 機能 | 形式 |
|---|---|
| `/summary` | 📝 箇条書き（話題ごとの流れ） |
| `/catch_up` | 📝 箇条書き（指定話題の時系列まとめ） |
| `/search` | 🔍 要約文 ＋ 関連メッセージへのDiscordリンク（複数） |
| 定期投稿 | 📝 箇条書き（/summaryと同形式） |

---

## For AI Agents

### Working In This Directory

- パッケージ管理は `uv`（`uv sync` / `uv add`）
- フォーマット: `ruff format .`、リント: `ruff check .`
- 環境変数は `.env` で管理。`config.yaml` にシークレットを書かない
- LLM呼び出しは常に `llm_client.py` 経由。直接インポート禁止
- **チャンク分割は行わない**。全テキストをそのまま LLM に渡す
- discord-minutes-bot のコードは参照・流用しない

### Testing Requirements

- テストランナー: `pytest`
- LLM呼び出し (`llm_client.py`) はモックでテスト
- DB操作はインメモリSQLiteでテスト
- `docker compose up` 一発で全サービスが起動することを確認する

### Common Patterns

- メッセージ保存は `db.py` に集約する（bot.py 内に SQL を書かない）
- `collector.py` はDB優先、DBになければ Discord API にフォールバックする
- TTL切れメッセージの削除は Bot 起動時と定期バッチの両方で行う
- LLMサーバーの起動待機は Docker の `depends_on: condition: service_healthy` に任せる

---

## Dependencies

### External

| パッケージ | 用途 |
|---|---|
| `py-cord >= 2.6` | Discord Bot フレームワーク |
| `aiosqlite` | 非同期 SQLite アクセス |
| `httpx` | llama-cpp-python HTTP サーバーへの非同期リクエスト |
| `PyYAML` | `config.yaml` 読み込み |
| `python-dotenv` | `.env` 読み込み |
| `apscheduler` | 定期自動投稿スケジューラ |

### LLM サービス

| 項目 | 内容 |
|---|---|
| モデル | Gemma4 26B (GGUF形式) |
| サーバー | llama-cpp-python (Docker コンテナ) |
| エンドポイント | `http://llm:8080/completion` |
| チャンク分割 | なし（全文を1リクエストで送信） |

### 共通環境

| 項目 | 内容 |
|---|---|
| OS | Linux (Arch Linux / Ubuntu 22.04 LTS) |
| Python | 3.12 |
| GPU | NVIDIA GTX 980 Ti (VRAM 6GB) ※LLMはCPUオフロードを想定 |
| RAM | 32GB |
| コンテナ | Docker / Docker Compose |

---

## 禁止事項

- 外部 AI API の使用（OpenAI API、Anthropic API 等）
- テキストのチャンク分割（コンテキストを失う処理）
- `DISCORD_TOKEN` を `config.yaml` またはソースコードにハードコードすること
- VC（音声チャンネル）のサポート追加
- discord-minutes-bot のコードをコピー・インポートすること

<!-- MANUAL: プロジェクト固有のメモはここ以降に追記 -->
