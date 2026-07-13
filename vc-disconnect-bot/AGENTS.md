<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-23 | Updated: 2026-05-28 -->

# vc-disconnect-bot

## Purpose

タイマーまたはアラーム時刻で Discord VC の全メンバー（または指定メンバー）を強制切断するBot。
LLM・DB・外部API一切なし。asyncio のみで完結するシンプルな設計。

---

## Key Files

| File | Description |
|------|-------------|
| `bot.py` | エントリーポイント・スラッシュコマンド定義・ギルド状態管理 (`_guild_states`) |
| `timer.py` | `GuildTimer` クラス（asyncio.sleep ベースのタイマー / アラーム）・`parse_alarm_time` / `fmt_jst` ユーティリティ |
| `config.yaml` | タイムゾーン・警告秒数 |
| `.env.example` | `DISCORD_TOKEN` テンプレート |
| `pyproject.toml` | Python 依存関係（uv 管理） |
| `docker-compose.yml` | 単一 bot サービス |
| `Dockerfile` | python:3.12-slim + uv |

---

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `tests/` | pytest テストスイート（see `tests/AGENTS.md`） |

---

## Architecture

```
スラッシュコマンド (/vc timer / /vc alarm / /vc kick-timer)
       ↓
bot.py: _arm_timer() → GuildTimer 生成・asyncio.create_task()
       ↓
timer.py: GuildTimer._run()
  ├─ asyncio.sleep(until warning)  → テキストチャンネルに警告送信
  └─ asyncio.sleep(warning_secs)   → _disconnect_all()
       ├─ member.move_to(None) × 対象メンバー（全員 or target_members）
       └─ voice_client.disconnect()（voice_client が None でなければ）
       ↓
finally: on_complete() → _guild_states から削除
```

### 状態管理

```python
# bot.py
_guild_states: dict[int, dict[int, GuildState]]
# guild_id → channel_id → GuildState

@dataclass
class GuildState:
    voice_client: discord.VoiceClient | None  # None = Bot未参加でタイマーのみ動作
    voice_channel: discord.VoiceChannel
    text_channel: discord.TextChannel         # コマンド実行チャンネル（通知先）
    task: asyncio.Task | None
    timer: GuildTimer | None
    mode: str                                 # "timer" | "alarm" | "kick-timer" | "none"
    trigger_at: datetime.datetime | None      # UTC aware
    target_members: list[int] | None          # None = 全員切断, リスト = 指定メンバーのみ
```

- タイマーは**永続化しない**。Bot 再起動で消える仕様
- 同一 VC に複数のタイマーは持てない（channel_id ごとに 1 エントリ）
- `on_voice_state_update` で VC の全人間が退出した場合、タイマーを**自動キャンセル**する

---

## Discord コマンド一覧

| コマンド | 動作 |
|---|---|
| `/vc join` | Bot を現在の VC に参加（タイマーなし） |
| `/vc timer <minutes>` | N 分後に全員切断（1〜1440分） |
| `/vc alarm <time>` | HH:MM JST に全員切断（過去の場合は翌日） |
| `/vc status` | 残り時間・切断予定時刻を表示 |
| `/vc cancel` | タイマーキャンセル & Bot 退出 |
| `/vc kick <user> [user2] [user3]` | 指定ユーザー（最大3人）を即時切断 |
| `/vc kick-timer <minutes> <user>` | N 分後に指定ユーザー 1 人を切断 |
| `/vc move <user> <channel>` | 指定ユーザーを別 VC チャンネルへ移動 |
| `/vc move-all <channel>` | 現在 VC の全員を別 VC チャンネルへ移動（他Bot〈music-bot 等〉を優先的に先へ移動し、取り残しを防ぐ） |

- `/vc timer` と `/vc alarm` は Bot 未参加の場合**自動参加**する
- Bot が既に別 VC にいる場合、タイマーは動作するが対象 VC には参加しない（`voice_client=None`）

---

## 必要 Discord 権限

| 権限 | 用途 |
|---|---|
| `Connect` | VC に接続する |
| `Move Members` | `member.move_to(None)` で切断 / `member.move_to(channel)` で移動 |
| `Send Messages` | 警告・通知メッセージ |
| `Use Application Commands` | スラッシュコマンド |

## 必要 Intent

- **Server Members Intent（`intents.members`）が必須** — `VoiceChannel.members` は `guild.get_member()` でキャッシュ済みメンバーしか返さない（`discord/channel.py` の実装）。この intent がオフだと、コマンド実行者以外の未キャッシュメンバーが `channel.members` から欠落し、`/vc move-all` や `/vc kick` などで実行者以外が認識されない不具合になる。Developer Portal でも Privileged Gateway Intents から有効化すること

---

## For AI Agents

### Working In This Directory

- パッケージ管理は `uv`（`uv sync` / `uv add`）
- フォーマット: `uv run ruff format .`、リント: `uv run ruff check .`
- テスト: `uv run pytest`
- 環境変数は `.env` で管理。`config.yaml` にシークレットを書かない
- タイムゾーン処理は stdlib の `zoneinfo.ZoneInfo` を使う（`pytz` 禁止）
- DB・LLM・外部API は追加しない
- `_guild_states` のキー構造は `guild_id → channel_id → GuildState`（2 階層）

### Testing Requirements

- テストランナー: `pytest` + `pytest-asyncio`（`asyncio_mode = "auto"`）
- `discord.VoiceClient` / `discord.Member` は `unittest.mock.MagicMock` でモック
- タイマーのテストは `trigger_at` を過去に設定して即時発火させるパターンを使う
- `target_members` の選択的切断ロジックも必ずテストする

---

## Dependencies

| パッケージ | 用途 |
|---|---|
| `py-cord[voice] >= 2.6` | Discord Bot フレームワーク（スラッシュコマンド） |
| `PyYAML >= 6.0` | `config.yaml` 読み込み |
| `python-dotenv >= 1.0` | `.env` 読み込み |

---

## 禁止事項

- 外部 AI API の使用（OpenAI API、Anthropic API 等）
- `DISCORD_TOKEN` を `config.yaml` またはソースコードにハードコードすること
- `pytz` や `dateutil` の追加（stdlib の `zoneinfo` で足りる）
- タイマー状態の DB 永続化（再起動リセットは仕様）
- 音声の録音・送信

<!-- MANUAL: プロジェクト固有のメモはここ以降に追記 -->
