<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-28 | Updated: 2026-05-28 -->

# tests

## Purpose

vc-disconnect-bot の pytest テストスイート。
`timer.py` のロジックを中心にテストする。`discord` オブジェクトはすべて `MagicMock` で代替し、
実際の Discord API・ネットワーク接続なしで動作する。

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | パッケージ初期化（空） |
| `test_timer.py` | `GuildTimer` / `parse_alarm_time` / `fmt_jst` のユニットテスト |

## For AI Agents

### Working In This Directory

- テスト実行: `uv run pytest`（vc-disconnect-bot/ ディレクトリから）
- `asyncio_mode = "auto"` 設定済み（`pyproject.toml`）— `@pytest.mark.asyncio` 不要
- `discord.VoiceClient` / `discord.VoiceChannel` / `discord.Member` はすべて `MagicMock` でモックする
- 実際の `asyncio.sleep` を使うテストは `trigger_at` を過去に設定して即時発火させる

### Testing Requirements

- `GuildTimer` のテストは `_make_timer()` ヘルパーを使って共通セットアップを再利用する
- `target_members` の選択的切断ロジック（指定メンバーのみ / 指定メンバー不在の場合）は必ずテストする
- `voice_client=None` のケース（Bot 未参加でタイマーのみ動作）もテストする
- `move_members` 権限なしのケースをテストする

### Common Patterns

```python
# 即時発火パターン（trigger_at を過去に設定）
trigger_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
task = timer.start()
await asyncio.wait_for(task, timeout=2.0)

# メンバーモックの作成
def _make_member(display_name: str, is_bot: bool = False) -> MagicMock:
    member = MagicMock()
    member.display_name = display_name
    member.bot = is_bot
    member.move_to = AsyncMock()
    return member
```

## Dependencies

### Internal

- `timer.py` — `GuildTimer` / `parse_alarm_time` / `fmt_jst`

### External

| パッケージ | 用途 |
|---|---|
| `pytest` | テストランナー |
| `pytest-asyncio` | 非同期テストサポート（`asyncio_mode = "auto"`） |

<!-- MANUAL: -->
