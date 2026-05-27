# 実装計画: vc-disconnect-bot 機能追加

**Status:** pending approval (consensus reached — Architect REVISE → Critic APPROVE)
**Spec:** `.omc/specs/deep-dive-vc-disconnect-bot-kino-tsuika.md`
**Iteration:** 2 (Architect revisions + Critic improvements applied)

---

## RALPLAN-DR Summary

### Principles
1. **既存動作を壊さない** — `/vc timer`, `/vc alarm`, `/vc status`, `/vc cancel`, `/vc join` の振る舞いを保持する
2. **最小侵襲変更** — 変更は `timer.py` と `bot.py` の2ファイルのみ（新ファイル不要）
3. **状態の単一真実源** — `_guild_states` dict のみで状態を管理し続ける（CLAUDE.md 制約）
4. **VC入居不問** — ボットがVCに入居していなくてもタイマーが動作する設計
5. **テスト先行** — 新機能には対応するテストを必ず追加する

### Decision Drivers (Top 3)
1. **py-cord制約: ギルドにつきVoiceClientは1つだけ** — 複数VCタイマーをbotが全て入居する形では実現不可
2. **永続化なし（CLAUDE.md仕様）** — `_guild_states` dict以外の状態管理手段は使わない
3. **後方互換性** — 既存の5コマンドが今まで通り動くことが必須

### Viable Options

**Option A（採用）: Nested dict + optional VoiceClient**
- `_guild_states: dict[int, dict[int, GuildState]]` (guild_id → channel_id → GuildState)
- `GuildState.voice_client: discord.VoiceClient | None`
- ボットは最初のVCのみ入居、後続VCはモニタリングのみ
- Pros: `voice_channel.members` でメンバー取得・`member.move_to()` で操作可能。py-cord制約を自然に回避。
- Cons: 全ての既存コードの `_guild_states[guild_id]` アクセスを `_guild_states[guild_id][channel_id]` に変更する必要がある

**Option B（却下）: Flat dict with tuple key**
- `_guild_states: dict[tuple[int, int], GuildState]` ((guild_id, channel_id) → GuildState)
- Pros: イテレーションがシンプル
- Cons: `guild_id` だけでのルックアップが必要な箇所でフィルタリングが必要。可読性が低い。Option Aで同等のシンプルさが得られるため却下。

---

## Requirements Summary

### 新コマンド
| コマンド | 機能 |
|---|---|
| `/vc kick <user1> [user2] [user3]` | 指定ユーザーを即時切断 |
| `/vc kick-timer <minutes> <user>` | N分後に指定ユーザーを切断 |
| `/vc move <user> <channel>` | 指定ユーザーを別VCへ移動 |
| `/vc move-all <channel>` | 現在VCの全員を別VCへ移動 |

### 既存コマンド変更
- `/vc timer`, `/vc alarm`: VC別独立タイマー（複数VC同時可）
- `/vc status`, `/vc cancel`: 呼び出し元VCのみ対象
- `on_voice_state_update`: 空チャンネルで自動キャンセル追加

---

## Acceptance Criteria

### AC-1: 複数VC同時タイマー
- [ ] `#vc-A` のメンバーが `/vc timer 30` を実行すると `#vc-A` にタイマーが設定される (`bot.py`)
- [ ] 同時に `#vc-B` のメンバーが `/vc timer 60` を実行できる（`_has_active_timer` が channel_id を考慮）
- [ ] `/vc status` は `ctx.author.voice.channel.id` でルックアップした自チャンネルの状態のみ返す
- [ ] `/vc cancel` は自チャンネルのタイマーのみキャンセルする（他VC影響なし）
- [ ] 各タイマーの asyncio.Task は独立して動作する

### AC-2: 空チャンネル自動停止
- [ ] `on_voice_state_update` で対象VCの全人間が退出した際にタイマーを自動キャンセルする
- [ ] 自動キャンセル時に `state.text_channel` へ通知メッセージを送信する
- [ ] ボットが入居していた場合 (`state.voice_client is not None`) はボットも退出する

### AC-3: 即時切断 (`/vc kick`)
- [ ] 指定ユーザーが呼び出し元と同じVCにいる場合のみ `member.move_to(None)` を実行できる
- [ ] 対象ユーザーが同VCにいない場合は ephemeral エラーを返す
- [ ] `Move Members` 権限チェックをコマンド起動時に実行する

### AC-4: タイマー切断 (`/vc kick-timer`)
- [ ] `GuildTimer(target_members=[user.id])` でタイマーを設定できる
- [ ] タイマー発火時に `target_members` に一致するユーザーのみを切断する
- [ ] `/vc cancel` で `kick-timer` も合わせてキャンセルされる（同一channel_idのstateを削除）
- [ ] 同一VCに `/vc timer`, `/vc alarm`, `/vc kick-timer` のいずれかが active なとき、`/vc kick-timer` は ephemeral エラーを返す（per-channel 1タイマー制約）

### AC-5: VC移動
- [ ] `/vc move @user #channel` で `member.move_to(destination_channel)` を呼べる
- [ ] `/vc move-all #channel` で現在VCの全人間メンバーを `destination_channel` へ移動できる
- [ ] 移動先がVoiceChannelでない場合は ephemeral エラーを返す（py-cord Option型でChannelではなくVoiceChannelを指定）

### AC-6: テスト継続
- [ ] `uv run pytest tests/` が全テスト通過（既存13件）
- [ ] `GuildTimer(target_members=[...])` の絞り込みテストが追加されている
- [ ] `GuildTimer(voice_client=None)` のテストが追加されている

---

## Implementation Steps

### Step 1: `timer.py` — GuildTimer を拡張

**1-1. `voice_client` を Optional に変更** (`timer.py:41-56`)

```python
class GuildTimer:
    def __init__(
        self,
        voice_client: discord.VoiceClient | None,  # None = bot not in VC
        voice_channel: discord.VoiceChannel,
        text_channel: discord.TextChannel,
        trigger_at: datetime.datetime,
        warning_seconds: int,
        on_complete: Callable[[], Awaitable[None]],
        target_members: list[int] | None = None,  # None = all humans
    ) -> None:
        ...
        self._target_members = target_members
```

**1-2. `_disconnect_all` に `target_members` フィルタリングを追加** (`timer.py:102-134`)

```python
async def _disconnect_all(self) -> None:
    channel = self._voice_channel
    perms = channel.permissions_for(channel.guild.me)

    if not perms.move_members:
        await self._text_channel.send(...)
        if self._voice_client and self._voice_client.is_connected():
            await self._voice_client.disconnect()
        return

    all_humans = [m for m in channel.members if not m.bot]
    if self._target_members is not None:
        members = [m for m in all_humans if m.id in self._target_members]
        label = "指定メンバーを切断"
    else:
        members = all_humans
        label = "全員を切断"

    if not members:
        await self._text_channel.send(
            f"ℹ️ 対象メンバーは既に {channel.mention} にいません"
        )
        if self._voice_client and self._voice_client.is_connected():
            await self._voice_client.disconnect()
        return

    await self._text_channel.send(
        f"🔔 時間になりました。{channel.mention} の{label}します（{len(members)}人）"
    )

    failed: list[str] = []
    for member in members:
        try:
            await member.move_to(None)
        except discord.Forbidden:
            failed.append(member.display_name)
        except discord.HTTPException as e:
            logger.warning("Failed to disconnect %s: %s", member.display_name, e)

    if failed:
        await self._text_channel.send(
            f"⚠️ 権限不足で切断できなかったメンバー: {', '.join(failed)}"
        )

    if self._voice_client and self._voice_client.is_connected():
        await self._voice_client.disconnect()
```

---

### Step 2: `bot.py` — 状態管理をチャンネルキーに変更

**2-1. `GuildState` に `target_members` フィールド追加** (`bot.py:26-35`)

```python
@dataclasses.dataclass
class GuildState:
    voice_client: discord.VoiceClient | None      # None = bot not in VC
    voice_channel: discord.VoiceChannel
    text_channel: discord.TextChannel
    task: asyncio.Task | None
    timer: GuildTimer | None
    mode: str                                      # "timer", "alarm", "kick-timer", "none"
    trigger_at: datetime.datetime | None
    target_members: list[int] | None = None        # None = all; list of user IDs for kick-timer
```

**2-2. `_guild_states` の型を変更** (`bot.py:37`)

```python
_guild_states: dict[int, dict[int, GuildState]] = {}
# guild_id → channel_id → GuildState
```

**2-3. `_has_active_timer` を channel_id 対応に変更** (`bot.py:40-42`)

```python
def _has_active_timer(guild_id: int, channel_id: int) -> bool:
    state = _guild_states.get(guild_id, {}).get(channel_id)
    return state is not None and state.task is not None and not state.task.done()
```

**2-4. `_cleanup` を channel_id 対応に変更** (`bot.py:45-46`)

```python
async def _cleanup(guild_id: int, channel_id: int) -> None:
    guild_ch = _guild_states.get(guild_id, {})
    guild_ch.pop(channel_id, None)
    if not guild_ch:
        _guild_states.pop(guild_id, None)
```

**2-5. `_arm_timer` を channel_id 対応に変更** (`bot.py:49-78`)

```python
def _arm_timer(
    guild_id: int,
    channel_id: int,
    voice_client: discord.VoiceClient | None,
    voice_channel: discord.VoiceChannel,
    text_channel: discord.TextChannel,
    trigger_at: datetime.datetime,
    mode: str,
    target_members: list[int] | None = None,
) -> None:
    async def on_complete() -> None:
        await _cleanup(guild_id, channel_id)

    timer = GuildTimer(
        voice_client=voice_client,
        voice_channel=voice_channel,
        text_channel=text_channel,
        trigger_at=trigger_at,
        warning_seconds=_WARNING_SECONDS,
        on_complete=on_complete,
        target_members=target_members,
    )
    task = timer.start()

    _guild_states.setdefault(guild_id, {})[channel_id] = GuildState(
        voice_client=voice_client,
        voice_channel=voice_channel,
        text_channel=text_channel,
        task=task,
        timer=timer,
        mode=mode,
        trigger_at=trigger_at,
        target_members=target_members,
    )
```

---

### Step 3: `bot.py` — 既存コマンドを多チャンネル対応に更新

**3-1. `/vc join`** (`bot.py:96-138`)
- `_has_active_timer(guild_id)` → `_has_active_timer(guild_id, channel.id)`
- 既存接続チェックを channel_id ベースに変更
- `_guild_states[guild_id]` → `_guild_states.setdefault(guild_id, {})[channel.id]`
- **ボットが既に別VCにいる場合の挙動を明示**: `ctx.guild.voice_client` が他のVCに接続中の場合はエラーを返す（`/vc join` はbotが入居していないチャンネルのみ対象。タイマー系コマンドと異なり、joinだけはbot在室を前提とするため二重接続は不可）:
  ```python
  existing_vc = ctx.guild.voice_client
  if existing_vc and existing_vc.is_connected() and existing_vc.channel != channel:
      await ctx.respond(
          f"❌ ボットはすでに {existing_vc.channel.mention} に参加しています。先に `/vc cancel` で退出してください",
          ephemeral=True,
      )
      return
  ```

**3-2. `/vc timer`** (`bot.py:141-177`)
> **Note:** `_get_or_connect` ヘルパー (`bot.py:81-93`) はStep 3-2の変更で機能的に不要になる。Step 3完了後に削除すること。
- `_has_active_timer(guild_id)` → `_has_active_timer(guild_id, channel.id)` (呼び出し元チャンネル)
- `_arm_timer(...)` の引数に `channel_id=channel.id` を追加
- `_get_or_connect` の動作変更: ギルドにすでにVoiceClientがある場合はNoneを返しbotは新規接続しない（`voice_client=None`で`_arm_timer`を呼ぶ）

  ```python
  # ギルドに既存VoiceClientがあるか確認
  existing_vc = ctx.guild.voice_client  # py-cord: Guildの現在VC接続
  if existing_vc and existing_vc.is_connected():
      # botは既に別VCにいる → 新規接続せずNoneで管理
      voice_client = None
  else:
      try:
          voice_client = await channel.connect()
      except Exception as e:
          ...
  _arm_timer(ctx.guild_id, channel.id, voice_client, channel, ctx.channel, trigger_at, "timer")
  ```

**3-3. `/vc alarm`** (`bot.py:180-214`) — `/vc timer` と同様の変更

**3-4. `/vc status`** (`bot.py:217-242`)
- 呼び出し元ユーザーがVCにいない場合はエラー返却
- `channel_id = ctx.author.voice.channel.id` でルックアップ
- **`mode_label` に `"kick-timer"` ケースを追加** (`bot.py:235` の二項演算子を三項に拡張):
  ```python
  mode_labels = {"timer": "タイマー", "alarm": "アラーム", "kick-timer": "キックタイマー"}
  mode_label = mode_labels.get(state.mode, state.mode)
  ```

  ```python
  if not ctx.author.voice or not ctx.author.voice.channel:
      await ctx.respond("❌ VCに参加してからステータスを確認してください", ephemeral=True)
      return
  channel_id = ctx.author.voice.channel.id
  state = _guild_states.get(ctx.guild_id, {}).get(channel_id)
  ```

**3-5. `/vc cancel`** (`bot.py:245-259`)
- 呼び出し元ユーザーがVCにいない場合はエラー返却
- `channel_id` でルックアップして対象stateのみキャンセル

  ```python
  if not ctx.author.voice or not ctx.author.voice.channel:
      await ctx.respond("❌ VCに参加してからキャンセルしてください", ephemeral=True)
      return
  channel_id = ctx.author.voice.channel.id
  guild_ch = _guild_states.get(ctx.guild_id, {})
  state = guild_ch.pop(channel_id, None)
  if not state:
      await ctx.respond("📭 このVCにキャンセルするタイマーがありません", ephemeral=True)
      return
  if not guild_ch:
      _guild_states.pop(ctx.guild_id, None)
  if state.timer is not None:
      await state.timer.cancel()
  if state.voice_client and state.voice_client.is_connected():
      await state.voice_client.disconnect()
  ```

---

### Step 4: `bot.py` — 新コマンドを追加

**4-1. `/vc kick`**

```python
@vc_group.command(name="kick", description="指定したユーザーをVCから即時切断します")
async def cmd_vc_kick(
    ctx: discord.ApplicationContext,
    user1: discord.Member = discord.Option(discord.Member, description="切断するユーザー"),
    user2: discord.Member = discord.Option(discord.Member, description="切断するユーザー2（任意）", required=False, default=None),
    user3: discord.Member = discord.Option(discord.Member, description="切断するユーザー3（任意）", required=False, default=None),
) -> None:
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.respond("❌ まずVCに参加してください", ephemeral=True)
        return
    channel = ctx.author.voice.channel
    perms = channel.permissions_for(ctx.guild.me)
    if not perms.move_members:
        await ctx.respond("❌ `メンバーを移動` 権限がありません", ephemeral=True)
        return
    targets = [u for u in [user1, user2, user3] if u is not None]
    not_in_vc = [u for u in targets if u.voice is None or u.voice.channel != channel]
    if not_in_vc:
        names = ", ".join(u.display_name for u in not_in_vc)
        await ctx.respond(f"❌ {names} は {channel.mention} にいません", ephemeral=True)
        return
    await ctx.respond(f"🔇 {', '.join(u.mention for u in targets)} を切断します")
    for user in targets:
        try:
            await user.move_to(None)
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.warning("kick failed for %s: %s", user.display_name, e)
```

**4-2. `/vc kick-timer`**

```python
@vc_group.command(name="kick-timer", description="N分後に指定ユーザーをVCから切断します")
async def cmd_vc_kick_timer(
    ctx: discord.ApplicationContext,
    minutes: int = discord.Option(int, description="切断までの分数（1〜1440）", min_value=1, max_value=1440),
    user: discord.Member = discord.Option(discord.Member, description="切断するユーザー"),
) -> None:
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.respond("❌ まずVCに参加してください", ephemeral=True)
        return
    channel = ctx.author.voice.channel
    if user.voice is None or user.voice.channel != channel:
        await ctx.respond(f"❌ {user.display_name} は {channel.mention} にいません", ephemeral=True)
        return
    if _has_active_timer(ctx.guild_id, channel.id):
        await ctx.respond(
            "❌ このVCにはすでにタイマーが動いています。`/vc cancel` でキャンセルしてください",
            ephemeral=True,
        )
        return
    perms = channel.permissions_for(ctx.guild.me)
    if not perms.move_members:
        await ctx.respond("❌ `メンバーを移動` 権限がありません", ephemeral=True)
        return
    trigger_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)
    await ctx.respond(
        f"⏱️ {minutes}分後（{fmt_jst(trigger_at)}）に {user.mention} を {channel.mention} から切断します"
    )
    _arm_timer(
        ctx.guild_id, channel.id, None, channel, ctx.channel,
        trigger_at, "kick-timer", target_members=[user.id]
    )
```

**4-3. `/vc move`**

```python
@vc_group.command(name="move", description="指定ユーザーを別のVCチャンネルへ移動します")
async def cmd_vc_move(
    ctx: discord.ApplicationContext,
    user: discord.Member = discord.Option(discord.Member, description="移動するユーザー"),
    channel: discord.VoiceChannel = discord.Option(discord.VoiceChannel, description="移動先のVCチャンネル"),
) -> None:
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.respond("❌ まずVCに参加してください", ephemeral=True)
        return
    src_channel = ctx.author.voice.channel
    perms = src_channel.permissions_for(ctx.guild.me)
    if not perms.move_members:
        await ctx.respond("❌ `メンバーを移動` 権限がありません", ephemeral=True)
        return
    if user.voice is None or user.voice.channel != src_channel:
        await ctx.respond(f"❌ {user.display_name} は {src_channel.mention} にいません", ephemeral=True)
        return
    await ctx.respond(f"📤 {user.mention} を {channel.mention} へ移動します")
    try:
        await user.move_to(channel)
    except (discord.Forbidden, discord.HTTPException) as e:
        await ctx.channel.send(f"❌ 移動に失敗しました: {e}")
```

**4-4. `/vc move-all`**

```python
@vc_group.command(name="move-all", description="現在のVCの全員を別のVCチャンネルへ移動します")
async def cmd_vc_move_all(
    ctx: discord.ApplicationContext,
    channel: discord.VoiceChannel = discord.Option(discord.VoiceChannel, description="移動先のVCチャンネル"),
) -> None:
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.respond("❌ まずVCに参加してください", ephemeral=True)
        return
    src_channel = ctx.author.voice.channel
    perms = src_channel.permissions_for(ctx.guild.me)
    if not perms.move_members:
        await ctx.respond("❌ `メンバーを移動` 権限がありません", ephemeral=True)
        return
    members = [m for m in src_channel.members if not m.bot]
    if not members:
        await ctx.respond(f"❌ {src_channel.mention} に移動対象のメンバーがいません", ephemeral=True)
        return
    await ctx.respond(f"📤 {src_channel.mention} の全員（{len(members)}人）を {channel.mention} へ移動します")
    failed: list[str] = []
    for member in members:
        try:
            await member.move_to(channel)
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.warning("move-all failed for %s: %s", member.display_name, e)
            failed.append(member.display_name)
    if failed:
        await ctx.channel.send(f"⚠️ 移動できなかったメンバー: {', '.join(failed)}")
```

---

### Step 5: `bot.py` — `on_voice_state_update` に自動キャンセルを追加

(`bot.py:262-289`)

**実行順序の明示 (Architect 指摘 #1):**
`state.timer.cancel()` を呼ぶと以下の順序で処理が進む:
1. `timer.cancel()` → asyncio タスクを `task.cancel()` で取り消し、`await task` で完了を待つ
2. `GuildTimer._run()` の `except asyncio.CancelledError: raise` が発火
3. `finally: await self._on_complete()` が呼ばれる (`timer.py:99-100`)
4. `_on_complete` = `_cleanup(guild_id, channel_id)` → `_guild_states` からエントリを削除
5. `cancel()` が返った時点で state エントリは既に削除されている
6. **ただし `state` はローカル変数として参照が生きているため、以降の `state.voice_client`, `state.text_channel` へのアクセスは安全**

```python
@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    if member.id == bot.user.id:
        return

    guild_id = member.guild.id
    guild_ch = _guild_states.get(guild_id)
    if not guild_ch:
        return

    # list() コピーで安全にイテレーション: _cleanup が別チャンネルのエントリを削除しても影響しない
    for channel_id, state in list(guild_ch.items()):
        if state.mode == "none":
            continue
        if before.channel == state.voice_channel and after.channel != state.voice_channel:
            human_members = [m for m in state.voice_channel.members if not m.bot]
            if not human_members:
                logger.info("All humans left %s, auto-cancelling timer", state.voice_channel.name)
                if state.timer:
                    await state.timer.cancel()
                    # 実行順序: cancel() → finally → on_complete → _cleanup (state削除)
                    # cancel()が返った後、stateローカル変数は生きているが_guild_statesからは削除済み
                if state.voice_client and state.voice_client.is_connected():
                    await state.voice_client.disconnect()
                await state.text_channel.send(
                    f"✅ {state.voice_channel.mention} から全員が退出したため、タイマーを自動キャンセルしました"
                )
```

---

### Step 6: `tests/test_timer.py` — 新テストケースを追加（既存ファイルに追記）

**6-1. `target_members` フィルタリングのテスト** (`tests/test_timer.py`)
- `target_members=[user1.id]` で user1 のみ切断、user2 は切断されない
- `target_members=[user1.id]` でそのユーザーがすでにいない場合のメッセージ確認

**6-2. `voice_client=None` のテスト** (`tests/test_timer.py`)
- `voice_client=None` でタイマーが正常に動作する（切断後にbotの `disconnect()` が呼ばれない）

---

## Risks and Mitigations

| リスク | 影響 | 軽減策 |
|---|---|---|
| py-cord: `ctx.guild.voice_client` の取得方法 | 中: guild.voice_clientがNoneを返す場合の処理 | `ctx.guild.voice_client` は py-cord 2.6以降でサポート。取得失敗時はNoneで処理 |
| `voice_channel.members` キャッシュ不整合 | 低: 小規模サーバーでは稀 | `intent` に `members` が含まれていることを前提（py-cordデフォルト） |
| `on_voice_state_update` の `timer.cancel()` とタイマー発火の競合 | 低: asyncio シングルスレッドで競合なし | asyncioはシングルスレッドなので基本的に競合しない |
| `/vc cancel` の二重削除 (`guild_ch.pop` + `on_complete→_cleanup`) | 低: `pop(key, None)` で安全に処理 | `None` デフォルト付き pop で KeyError 発生しない |
| `/vc move` で `discord.VoiceChannel` Option が正しく機能するか | 中: py-cord のオプション型選択 | py-cord の `ChannelType` フィルタでボイスチャンネルのみ表示するオプション追加が必要な可能性 |

---

## Verification Steps

1. `cd vc-disconnect-bot && uv run pytest tests/ -v` → 全テスト通過
2. `uv run ruff check . && uv run ruff format --check .` → エラー0
3. Docker compose up で起動確認
4. ローカルDiscordサーバーで手動確認:
   - 2つのVCチャンネルで同時に `/vc timer` を実行できる
   - 一方のVCから全員退出で自動キャンセル（もう一方に影響なし）
   - `/vc kick @user` で即時切断
   - `/vc kick-timer 1 @user` で1分後に切断
   - `/vc move @user #other-vc` で移動
   - `/vc move-all #other-vc` で全員移動

---

## ADR

### Decision
`_guild_states` の型を `dict[int, GuildState]` から `dict[int, dict[int, GuildState]]`（guild_id → channel_id → GuildState）に変更し、`GuildState.voice_client` を `Optional` にする。

### Drivers
1. py-cord はギルドにつき VoiceClient を1つしか許可しない
2. 複数VC同時タイマーを実現するためには「ボットが全VCに入居する」アーキテクチャが不可能
3. `member.move_to(None)` と `voice_channel.members` はボット入居なしで動作する

### Alternatives Considered
- **Flat dict with tuple key** `dict[tuple[int,int], GuildState]`: 却下。既存コードのルックアップパターン（`guild_id` のみ）に適合しない。
- **複数ボットインスタンス**: スコープ外（CLAUDE.md「1インスタンス」制約）。

### Why Chosen
Nested dict は既存コードの変更量を最小化しつつ、channel_id の独立管理を実現する。`voice_client=None` の optional 化は py-cord 制約を自然に回避する。

### Consequences
- `_guild_states[guild_id]` へのアクセスが全て `_guild_states.get(guild_id, {})[channel_id]` または `_guild_states.get(guild_id, {}).get(channel_id)` になる
- `_cleanup`, `_arm_timer`, `_has_active_timer` のシグネチャに `channel_id: int` が追加される

### Follow-ups
- `config.yaml` の `timezone` キーが実行時に参照されていない（dead config）— 別イシューとして対処
- `_disconnect_all` の `asyncio.gather` 化（並列切断）— 大規模サーバー向けの最適化として検討

---

## Changelog
- v1: 初期Plannerドラフト（consensus loop iteration 1）
- v2: Architect REVISE対応 — AC-4に1タイマー制約追加・status mode_label拡張・Step 5の実行順序ドキュメント化・/vc joinの別VC在室エラー追加
- v2.1: Critic APPROVE — `_get_or_connect`削除メモ追加・list()コピーコメント追加・AC-6テストファイル名明記（consensus完了）
