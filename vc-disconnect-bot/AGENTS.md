<!-- Parent: ../AGENTS.md -->

# vc-disconnect-bot

## Purpose

タイマーまたはアラーム時刻で Discord VC の全メンバーを強制切断するBot。
LLM・DB・外部API一切なし。asyncioのみで完結するシンプルな設計。

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

## Architecture

```
スラッシュコマンド (/vc timer / /vc alarm)
       ↓
bot.py: _ensure_joined() → VCに接続
       ↓
bot.py: _arm_timer() → GuildTimer 生成・asyncio.create_task()
       ↓
timer.py: GuildTimer._run()
  ├─ asyncio.sleep(until warning)  → テキストチャンネルに警告送信
  └─ asyncio.sleep(warning_secs)   → _disconnect_all()
       ├─ member.move_to(None) × 全員
       └─ voice_client.disconnect()
       ↓
finally: on_complete() → _guild_states から削除
```

### 状態管理

```python
# bot.py
_guild_states: dict[int, GuildState]  # guild_id → GuildState

@dataclass
class GuildState:
    voice_client: discord.VoiceClient
    voice_channel: discord.VoiceChannel
    text_channel: discord.TextChannel   # コマンド実行チャンネル（通知先）
    task: asyncio.Task
    timer: GuildTimer
    mode: str                           # "timer" | "alarm" | "none"
    trigger_at: datetime.datetime       # UTC aware
```

タイマーは**永続化しない**。Bot再起動で消える仕様。

---

## Discord コマンド一覧

| コマンド | 動作 |
|---|---|
| `/vc join` | Bot を現在の VC に参加（タイマーなし） |
| `/vc timer <minutes>` | N 分後に全員切断（1〜1440分） |
| `/vc alarm <time>` | HH:MM JST に全員切断（過去の場合は翌日） |
| `/vc status` | 残り時間・切断予定時刻を表示 |
| `/vc cancel` | タイマーキャンセル & Bot 退出 |

`/vc timer` と `/vc alarm` は Bot 未参加の場合**自動参加**する。

---

## 必要 Discord 権限

| 権限 | 用途 |
|---|---|
| `Connect` | VC に接続する |
| `Move Members` | `member.move_to(None)` で全員切断 |
| `Send Messages` | 警告・通知メッセージ |
| `Use Application Commands` | スラッシュコマンド |

---

## For AI Agents

### Working In This Directory

- パッケージ管理は `uv`（`uv sync` / `uv add`）
- フォーマット: `uv run ruff format .`、リント: `uv run ruff check .`
- テスト: `uv run pytest`
- 環境変数は `.env` で管理。`config.yaml` にシークレットを書かない
- タイムゾーン処理は stdlib の `zoneinfo.ZoneInfo` を使う（`pytz` 禁止）
- DB・LLM・外部API は追加しない

### Testing Requirements

- テストランナー: `pytest` + `pytest-asyncio`（`asyncio_mode = "auto"`）
- `discord.VoiceClient` / `discord.Member` は `unittest.mock.MagicMock` でモック
- タイマーの時刻計算は実際の `asyncio.sleep` を短時間で実行してテスト

---

## Dependencies

| パッケージ | 用途 |
|---|---|
| `py-cord >= 2.6` | Discord Bot フレームワーク（スラッシュコマンド） |
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
