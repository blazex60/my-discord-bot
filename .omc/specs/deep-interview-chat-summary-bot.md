# Deep Interview Spec: chat-summary-bot

## Metadata
- Interview ID: csbv1
- Rounds: 9
- Final Ambiguity Score: 17%
- Type: greenfield
- Generated: 2026-04-22
- Threshold: 20%
- Status: PASSED

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.85 | 40% | 0.340 |
| Constraint Clarity | 0.83 | 30% | 0.249 |
| Success Criteria | 0.80 | 30% | 0.240 |
| **Total Clarity** | | | **0.829** |
| **Ambiguity** | | | **17%** |

---

## Goal

カオスな雑談Discordサーバーのテキストチャンネルを対象に、「過去の会話を探しやすくする」「離席中の話題に短時間で追いつけるようにする」ことを目的とした チャット要約・検索Botを構築する。VC（音声チャンネル）は対象外。

---

## Constraints

- **言語/ランタイム**: Python 3.12、パッケージ管理は uv
- **Discord ライブラリ**: py-cord（または discord.py）
- **LLM**: Gemma4 26B を llama-cpp-python HTTP サーバーとして動かす
- **コンテナ**: Docker Compose で2サービス構成
  - サービス1: Discord Bot（Python）
  - サービス2: llama-cpp-python HTTP サーバー（Gemma4 26B モデル搭載）
- **チャンク分割なし**: コンテキストを失わないよう、テキストは分割せずにそのままLLMへ渡す
- **メッセージ取得**: Discord API（`channel.history()`）でリアルタイム取得 + ローカルDBキャッシュ
- **DB**: SQLite（ローカル永続化）＋TTLによる自動削除（期間は `config.yaml` で設定可能）
- **監視チャンネル**: デフォルト全チャンネル。管理者が除外リストを設定できる
- **自動投稿**: デフォルト無効。コマンドで有効化・スケジュール設定できる
- **外部AI API**: 使用禁止（OpenAI・Anthropic等）
- **フォーマッター**: ruff

---

## Non-Goals

- VC（音声チャンネル）のサポート
- コンテキスト分割（チャンク分割）処理
- 外部AIサービスへの依存
- discord-minutes-bot のコード共用（完全に独立した設計）

---

## Acceptance Criteria

- [ ] `/summary [件数]` を打つと、直近N件のメッセージを箇条書きで要約して返す
- [ ] `/search [キーワード]` を打つと、関連会話の要約文＋各メッセージへのDiscordリンクを返す
- [ ] `/catch_up [話題]` を打つと、指定した話題の流れを箇条書きで要約して返す
- [ ] `/watch add #channel` / `/watch remove #channel` で監視除外チャンネルを管理できる
- [ ] `/autopost set [cron式]` で定期投稿スケジュールを設定できる（デフォルト無効）
- [ ] `/autopost off` で定期投稿を停止できる
- [ ] BotがDBに保存したメッセージはTTL経過後に自動削除される
- [ ] TTLとDB保存期間は `config.yaml` で設定可能である
- [ ] Docker Compose 一発で全サービスが起動する（`docker compose up`）
- [ ] llama-cpp-python HTTP サーバーがヘルスチェックに応答するまでBotが待機する

---

## Assumptions Exposed & Resolved

| 前提 | どう問いただしたか | 決定 |
|------|-------------------|------|
| 機能の優先度 | どれがメインか？ | 3機能すべて同等 |
| 起動トリガー | コマンド or 自動？ | コマンド主導＋自動投稿はオプション（デフォルト無効） |
| AI処理方式 | ローカル or 外部API？ | llama.cpp + Gemma4 26B（ローカル） |
| コンテナ構成 | 何をどう分けるか？ | Docker Compose で Bot + LLMサーバーの2サービス |
| データソース | Discord API都度取得 or ローカルキャッシュ？ | ローカルDB＋TTL（Discordより少し長い寿命） |
| 監視チャンネル | 全部 or 選択式？ | 全チャンネル＋除外リスト |
| 検索結果形式 | 要約 or リンク or 両方？ | 要約＋Discordリンク |

---

## Technical Context

### アーキテクチャ概要

```
[Discord チャンネル]
       ↓ on_message イベント（全チャンネル、除外リスト以外）
[bot.py]  ── SQLite DB にメッセージを保存（TTL付き）
       ↓ コマンド受信
[コマンドハンドラ]
       ↓
[collector.py]  ── DB / Discord API からメッセージ取得
       ↓
[llm_client.py]  ── llama-cpp-python HTTP API を呼び出し
       ↓
[Gemma4 26B (Docker サービス)]  ── 要約・関連抽出を生成
       ↓
[bot.py]  ── Discord に返信（箇条書き / 要約+リンク）
```

### Docker Compose 構成

```yaml
services:
  bot:
    build: .
    depends_on:
      llm:
        condition: service_healthy
    environment:
      - LLM_URL=http://llm:8080

  llm:
    image: ghcr.io/ggerganov/llama.cpp:server
    volumes:
      - ./models:/models
    command: -m /models/gemma4-26b.gguf --port 8080
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
```

### SQLite スキーマ（案）

```sql
CREATE TABLE messages (
  id          TEXT PRIMARY KEY,   -- Discord message ID
  channel_id  TEXT NOT NULL,
  author_name TEXT NOT NULL,
  content     TEXT NOT NULL,
  created_at  INTEGER NOT NULL,   -- Unix timestamp
  expires_at  INTEGER NOT NULL    -- TTL: Unix timestamp
);

CREATE TABLE config (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
```

---

## Ontology (Key Entities)

| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| Message | core domain | id, channel_id, author_name, content, created_at, expires_at | belongs to Channel |
| Channel | core domain | id, name, is_excluded | has many Messages |
| Summary | core domain | content (bullet list), generated_at | derived from Messages |
| SearchResult | supporting | query, summary, message_links[] | derived from Messages |
| AutoPostSchedule | supporting | cron_expr, channel_id, enabled | targets Channel |
| LLMClient | external system | url (HTTP endpoint) | called by Summary, SearchResult |

---

## Ontology Convergence

| ラウンド | エンティティ数 | New | Changed | Stable | 安定率 |
|---------|-------------|-----|---------|--------|--------|
| 1 | 2 | 2 | - | - | - |
| 3 | 4 | 2 | 0 | 2 | 50% |
| 6 | 5 | 1 | 0 | 4 | 80% |
| 9 | 6 | 1 | 0 | 5 | 83% |

---

## Interview Transcript

<details>
<summary>全Q&A（9ラウンド）</summary>

### Round 1
**Q:** このBotが最も中心的に解決したい問題は何ですか？
**A:** 複数の目的を同等に（検索・追いつき・定期まとめ）
**Ambiguity:** 74% (Goal: 0.35, Constraints: 0.10, Criteria: 0.10)

### Round 2
**Q:** Botの要約・検索機能は主にコマンド型か自動投稿型か？
**A:** 基本はコマンド。定期投稿はコマンドから設定可能（デフォルトfalse）
**Ambiguity:** 61%

### Round 3
**Q:** 要約・AI処理について、どのアプローチを想定していますか？
**A:** llama.cppでGemma4:26bを動かす。Dockerコンテナ。チャンク分割なし。検索にDiscord API使用。AIは曖昧なニュアンス抽出に活用。
**Ambiguity:** 54%

### Round 4
**Q:** 完成したBotを実際に使ってくれたユーザーが「これは良い！」と思う具体的なシーンは？
**A:** 両方同等に（追いつき＋検索）
**Ambiguity:** 49%

### Round 5
**Q:** llama.cppでGemma4 26Bを動かす環境とコンテナの構成は？
**A:** Docker ComposeでllmmcpbpythonのHTTPサーバーを別サービスとして立てる
**Ambiguity:** 38%

### Round 6
**Q:** ユーザーが /summary を打ったとき、Botの返答はどんな形式が理想ですか？
**A:** 箇条書きの箇条（bullet list）
**Ambiguity:** 31%

### Round 7
**Q:** 追いつき・検索のためのメッセージ履歴はどこから取得しますか？
**A:** ローカルDBにキャッシュ。一定期間を過ぎたら削除（Discord直接取得より少し長い寿命）
**Ambiguity:** 27%

### Round 8
**Q:** Botはどのチャンネルのメッセージを監視・保存しますか？
**A:** 全チャンネル＋除外リスト
**Ambiguity:** 23%

### Round 9
**Q:** ユーザーが /search アニメ と打ったとき、Botは何を返しますか？
**A:** 要約＋リンク
**Ambiguity:** 17% ✅

</details>
