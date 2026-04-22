# chat-summary-bot 実装計画

## RALPLAN-DR Summary

### Principles
1. **単一責務**: 各ファイルは1つの役割のみ（DB操作、LLM呼び出し、コマンド処理）
2. **非同期ファースト**: Discord API・DB・HTTP呼び出しはすべて async/await
3. **設定外部化**: すべてのパラメータは `config.yaml` か `.env` で制御
4. **LLM呼び出しは薄いラッパーのみ**: llm_client.py はHTTP呼び出しのみ担当し、プロンプト構築は呼び出し側
5. **コンテナ境界を尊重**: BotコンテナはLLMコンテナのURLのみ知る

### Decision Drivers
1. チャンク分割なし制約 → コンテキスト長に収まるメッセージ件数を動的に制限する必要がある
2. Docker Compose の起動順序管理 → LLMサーバーのヘルスチェック待機が必要
3. 全チャンネル監視 + TTL → on_message でメッセージを逐次保存、TTL削除のバックグラウンドタスクが必要

### Viable Options

**Option A: モノリシック bot.py（全処理を1ファイル）**
- Pros: シンプル、ファイル数少ない
- Cons: テスト困難、責務が混在、将来の拡張が難しい
- → **却下**: テスタビリティと責務分離の原則に違反

**Option B: 機能別ファイル分割（採用）**
- Pros: テスト容易、責務明確、並行開発可能
- Cons: ファイル数が増える
- → **採用**: Principleの単一責務と一致

---

## 実装ステップ

### Step 0: プロジェクト初期化
- `pyproject.toml`、`uv.lock`、`.env.example`、`config.yaml` を作成
- `ruff` 設定を `pyproject.toml` に追加
- `.gitignore`（data/、models/、.venv/、.env）

### Step 1: Docker Compose 基盤
- `docker-compose.yml` (2サービス: bot + llm)
- `Dockerfile` (Botコンテナ用)
- llm サービスは `ghcr.io/ggerganov/llama.cpp:server` イメージを使用
- healthcheck: `curl http://localhost:8080/health`
- bot は `depends_on: llm: condition: service_healthy`

### Step 2: DB 層 (`db.py`)
- `aiosqlite` で SQLite 非同期アクセス
- `init_db()`: テーブル作成（messages, config）
- `save_message(msg)`: メッセージ保存（expires_at = now + TTL）
- `get_messages(channel_id, limit)`: チャンネル別取得
- `search_messages(query, limit)`: 全文検索（LIKE句）
- `delete_expired()`: TTL切れメッセージ削除
- `get_config(key)` / `set_config(key, value)`: 設定CRUD

### Step 3: LLM クライアント (`llm_client.py`)
- `httpx.AsyncClient` で llama-cpp-python HTTP API を呼び出す
- `complete(prompt: str) -> str`: `/completion` エンドポイントへ POST
- タイムアウト設定（config.yaml で指定）
- LLMサーバー未応答時は `LLMUnavailableError` を raise

### Step 4: コレクター (`collector.py`)
- `fetch_recent(channel, limit)`: DB優先、不足分はDiscord APIで補完
- `fetch_by_topic(channels, topic_hint, limit)`: DBのsearch_messagesを使用
- メッセージはDBの型 `dict` に正規化して返す
- **動的トランケーション**: 取得後にトークン数を概算（`len(content) // 4`）し、`n_ctx - prompt_overhead - max_tokens` を超えないよう末尾から切り詰める。切り詰めが発生した場合は Discord 返信に「（古いメッセージは省略しました）」を付記する

### Step 5: Discord Bot 本体 (`bot.py`)
- `on_ready`: `init_db()` + TTL削除バックグラウンドタスク起動
- `on_message`: 除外チャンネルでなければ `db.save_message()` を呼ぶ
- コマンド登録:
  - `/summary [count=50]`
  - `/search <query>`
  - `/catch_up <topic>`
  - `/watch add/remove <channel>`
  - `/autopost set <cron> / off`

### Step 6: スケジューラー (`scheduler.py`)
- `apscheduler.AsyncIOScheduler` を使用
- `start_autopost(cron_expr, channel_id)`: スケジュール登録
- `stop_autopost()`: スケジュール停止
- スケジュール設定は DB の config テーブルに永続化（再起動後も復元）

### Step 7: プロンプト定義 (`prompts.py`)
- `build_summary_prompt(messages)`: 要約プロンプト
- `build_search_prompt(messages, query)`: 検索・関連抽出プロンプト
- `build_catchup_prompt(messages, topic)`: 追いつき要約プロンプト
- すべて日本語出力を指示するシステムプロンプト付き

### Step 8: テスト (`tests/`)
- `test_db.py`: インメモリSQLiteでCRUD・TTL・設定テスト
- `test_llm_client.py`: httpxをモックしてHTTP呼び出しテスト
- `test_collector.py`: DB/Discord APIのフォールバックテスト
- `test_prompts.py`: プロンプトの整合性テスト

---

## ファイル構成

```
chat-summary-bot/
├── bot.py              # エントリーポイント・コマンド・on_message
├── collector.py        # メッセージ取得ロジック
├── db.py               # SQLite操作・TTL管理
├── llm_client.py       # llama-cpp-python HTTP API クライアント
├── prompts.py          # LLMプロンプト定義
├── scheduler.py        # 定期投稿スケジューラ
├── config.yaml         # 設定（TTL・LLM URL等）
├── .env.example        # シークレットテンプレート
├── pyproject.toml      # Python依存関係
├── Dockerfile          # Botコンテナ
├── docker-compose.yml  # 2サービス構成
├── models/             # Gemma4 26B GGUFモデル (.gitignore)
├── data/               # SQLiteデータベース (.gitignore)
└── tests/
    ├── test_db.py
    ├── test_llm_client.py
    ├── test_collector.py
    └── test_prompts.py
```

---

## Acceptance Criteria（テスト可能）

- [ ] `docker compose up` で全サービスが起動し、Botがオンラインになる
- [ ] `/summary 20` でDBから20件のメッセージを取得し箇条書き要約を返す
- [ ] `/search アニメ` で関連メッセージの要約＋Discordリンクを返す
- [ ] `/catch_up ゲーム` でゲーム話題の流れを箇条書きで返す
- [ ] `/watch add #secret` 後、#secret のメッセージがDBに保存されない
- [ ] `/autopost set "0 9 * * *"` で毎朝9時に要約が投稿される
- [ ] `/autopost off` で定期投稿が止まる
- [ ] TTL経過後のメッセージがDBから自動削除される
- [ ] LLMサーバー未起動時にBot起動が失敗せずエラーメッセージを返す
- [ ] `pytest tests/` が全テスト通過する
- [ ] `/summary 200` を打ったとき、LLMへの入力が `n_ctx - 3000` トークン以内に収まっている
- [ ] トークン切り詰めが発生した場合、返答に「（古いメッセージは省略しました）」が付記される
- [ ] LLMサーバーが返答不正（空文字・タイムアウト）の場合、Botが ❌ エラーメッセージを返す

---

## config.yaml（デフォルト値）

```yaml
discord:
  command_prefix: "/"

llm:
  url: "http://llm:8080"
  timeout_seconds: 120
  max_tokens: 2048

storage:
  db_path: "data/messages.db"
  ttl_days: 30
  max_messages_per_query: 80   # n_ctx=8192 から prompt+output 約3000トークンを引いた安全上限

monitoring:
  excluded_channels: []

autopost:
  enabled: false
  default_channel: null
```
