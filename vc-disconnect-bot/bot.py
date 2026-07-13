import asyncio
import dataclasses
import datetime
import logging
import os

import discord
import yaml
from dotenv import load_dotenv

from timer import GuildTimer, fmt_jst, parse_alarm_time

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

with open("config.yaml", encoding="utf-8") as f:
    _CONFIG = yaml.safe_load(f)

_WARNING_SECONDS: int = _CONFIG["bot"]["default_warning_seconds"]

bot = discord.Bot()
vc_group = bot.create_group("vc", "VCタイマー・アラーム管理")


@dataclasses.dataclass
class GuildState:
    voice_client: discord.VoiceClient | None
    voice_channel: discord.VoiceChannel
    text_channel: discord.TextChannel
    task: asyncio.Task | None
    timer: GuildTimer | None
    mode: str  # "timer", "alarm", "kick-timer", "none"
    trigger_at: datetime.datetime | None
    target_members: list[int] | None = None


_guild_states: dict[int, dict[int, GuildState]] = {}
# guild_id → channel_id → GuildState


def _has_active_timer(guild_id: int, channel_id: int) -> bool:
    state = _guild_states.get(guild_id, {}).get(channel_id)
    return state is not None and state.task is not None and not state.task.done()


async def _cleanup(guild_id: int, channel_id: int) -> None:
    guild_ch = _guild_states.get(guild_id, {})
    guild_ch.pop(channel_id, None)
    if not guild_ch:
        _guild_states.pop(guild_id, None)


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


@vc_group.command(name="join", description="ボットを現在のVCに参加させます（タイマーなし）")
async def cmd_vc_join(ctx: discord.ApplicationContext) -> None:
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.respond("❌ まずVCに参加してください", ephemeral=True)
        return

    channel = ctx.author.voice.channel

    if _has_active_timer(ctx.guild_id, channel.id):
        state = _guild_states[ctx.guild_id][channel.id]
        await ctx.respond(
            f"❌ すでに {state.voice_channel.mention} でタイマーが動作中です。`/vc cancel` で先にキャンセルしてください",
            ephemeral=True,
        )
        return

    # Check if bot is already in a different VC
    existing_vc = ctx.guild.voice_client
    if existing_vc and existing_vc.is_connected() and existing_vc.channel != channel:
        await ctx.respond(
            f"❌ ボットはすでに {existing_vc.channel.mention} に参加しています。先に `/vc cancel` で退出してください",
            ephemeral=True,
        )
        return

    existing_state = _guild_states.get(ctx.guild_id, {}).get(channel.id)
    if (
        existing_state
        and existing_state.voice_client
        and existing_state.voice_client.is_connected()
    ):
        await ctx.respond(
            f"❌ すでに {existing_state.voice_channel.mention} に参加しています",
            ephemeral=True,
        )
        return

    perms = channel.permissions_for(ctx.guild.me)
    if not perms.connect:
        await ctx.respond(f"❌ {channel.mention} に接続する権限がありません", ephemeral=True)
        return

    await ctx.respond(
        f"✅ {channel.mention} に参加しました。`/vc timer` または `/vc alarm` でタイマーを設定してください"
    )

    voice_client = await channel.connect()
    _guild_states.setdefault(ctx.guild_id, {})[channel.id] = GuildState(
        voice_client=voice_client,
        voice_channel=channel,
        text_channel=ctx.channel,
        task=None,
        timer=None,
        mode="none",
        trigger_at=None,
    )


@vc_group.command(name="timer", description="N分後にVCの全員を切断します")
async def cmd_vc_timer(
    ctx: discord.ApplicationContext,
    minutes: int = discord.Option(
        int, description="切断までの分数（1〜1440）", min_value=1, max_value=1440
    ),
) -> None:
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.respond("❌ まずVCに参加してください", ephemeral=True)
        return

    channel = ctx.author.voice.channel

    if _has_active_timer(ctx.guild_id, channel.id):
        await ctx.respond(
            f"❌ {channel.mention} にはすでにタイマーが動いています。`/vc cancel` で先にキャンセルしてください",
            ephemeral=True,
        )
        return

    perms = channel.permissions_for(ctx.guild.me)
    if not perms.connect:
        await ctx.respond(f"❌ {channel.mention} に接続する権限がありません", ephemeral=True)
        return

    trigger_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)

    await ctx.respond(
        f"⏱️ {minutes}分後（{fmt_jst(trigger_at)}）に {channel.mention} の全員を切断します"
    )

    # Bot joins only if not already in a VC in this guild
    existing_vc = ctx.guild.voice_client
    if existing_vc and existing_vc.is_connected():
        voice_client = None  # Already in another VC; manage timer without joining
        await ctx.channel.send(
            f"ℹ️ ボットはすでに {existing_vc.channel.mention} にいるため {channel.mention} には参加しませんが、タイマーは動作します"
        )
    else:
        try:
            voice_client = await channel.connect()
        except Exception as e:
            logger.error("VC connect failed: %s", e)
            await ctx.channel.send("❌ VCへの接続に失敗しました。タイマーをキャンセルします。")
            return

    _arm_timer(
        ctx.guild_id, channel.id, voice_client, channel, ctx.channel, trigger_at, mode="timer"
    )


@vc_group.command(name="alarm", description="指定時刻（JST）にVCの全員を切断します")
async def cmd_vc_alarm(
    ctx: discord.ApplicationContext,
    time: str = discord.Option(str, description="切断時刻 HH:MM（例: 22:00）"),
) -> None:
    trigger_at = parse_alarm_time(time)
    if trigger_at is None:
        await ctx.respond("❌ 時刻の形式が正しくありません（例: 22:00）", ephemeral=True)
        return

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.respond("❌ まずVCに参加してください", ephemeral=True)
        return

    channel = ctx.author.voice.channel

    if _has_active_timer(ctx.guild_id, channel.id):
        await ctx.respond(
            f"❌ {channel.mention} にはすでにタイマーが動いています。`/vc cancel` で先にキャンセルしてください",
            ephemeral=True,
        )
        return

    perms = channel.permissions_for(ctx.guild.me)
    if not perms.connect:
        await ctx.respond(f"❌ {channel.mention} に接続する権限がありません", ephemeral=True)
        return

    await ctx.respond(f"⏰ {fmt_jst(trigger_at)} に {channel.mention} の全員を切断します")

    existing_vc = ctx.guild.voice_client
    if existing_vc and existing_vc.is_connected():
        voice_client = None
        await ctx.channel.send(
            f"ℹ️ ボットはすでに {existing_vc.channel.mention} にいるため {channel.mention} には参加しませんが、タイマーは動作します"
        )
    else:
        try:
            voice_client = await channel.connect()
        except Exception as e:
            logger.error("VC connect failed: %s", e)
            await ctx.channel.send("❌ VCへの接続に失敗しました。タイマーをキャンセルします。")
            return

    _arm_timer(
        ctx.guild_id, channel.id, voice_client, channel, ctx.channel, trigger_at, mode="alarm"
    )


@vc_group.command(name="status", description="現在のVCのタイマー状態を表示します")
async def cmd_vc_status(ctx: discord.ApplicationContext) -> None:
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.respond("❌ VCに参加してからステータスを確認してください", ephemeral=True)
        return

    channel_id = ctx.author.voice.channel.id
    state = _guild_states.get(ctx.guild_id, {}).get(channel_id)

    if not state or state.task is None or state.task.done():
        await ctx.respond("📭 現在のVCにアクティブなタイマーはありません", ephemeral=True)
        return

    remaining = state.timer.seconds_remaining()
    minutes, seconds = divmod(int(remaining), 60)
    hours, minutes = divmod(minutes, 60)

    if hours > 0:
        remaining_str = f"{hours}時間{minutes}分{seconds}秒"
    elif minutes > 0:
        remaining_str = f"{minutes}分{seconds}秒"
    else:
        remaining_str = f"{seconds}秒"

    mode_labels = {"timer": "タイマー", "alarm": "アラーム", "kick-timer": "キックタイマー"}
    mode_label = mode_labels.get(state.mode, state.mode)

    target_info = ""
    if state.target_members:
        target_info = f"\n• 対象: {len(state.target_members)}人のメンバー"

    await ctx.respond(
        f"📊 **VC切断タイマー**\n"
        f"• チャンネル: {state.voice_channel.mention}\n"
        f"• モード: {mode_label}\n"
        f"• 切断予定: {fmt_jst(state.trigger_at)}\n"
        f"• 残り: {remaining_str}"
        f"{target_info}"
    )


@vc_group.command(name="cancel", description="現在のVCのタイマーをキャンセルしてVCから退出します")
async def cmd_vc_cancel(ctx: discord.ApplicationContext) -> None:
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

    await ctx.respond(f"✅ {state.voice_channel.mention} のタイマーをキャンセルしました")


@vc_group.command(name="kick", description="指定したユーザーをVCから即時切断します")
async def cmd_vc_kick(
    ctx: discord.ApplicationContext,
    user1: discord.Member = discord.Option(discord.Member, description="切断するユーザー"),
    user2: discord.Member = discord.Option(
        discord.Member, description="切断するユーザー2（任意）", required=False, default=None
    ),
    user3: discord.Member = discord.Option(
        discord.Member, description="切断するユーザー3（任意）", required=False, default=None
    ),
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


@vc_group.command(name="kick-timer", description="N分後に指定ユーザーをVCから切断します")
async def cmd_vc_kick_timer(
    ctx: discord.ApplicationContext,
    minutes: int = discord.Option(
        int, description="切断までの分数（1〜1440）", min_value=1, max_value=1440
    ),
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
            f"❌ {channel.mention} にはすでにタイマーが動いています。`/vc cancel` でキャンセルしてください",
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
        ctx.guild_id,
        channel.id,
        None,
        channel,
        ctx.channel,
        trigger_at,
        "kick-timer",
        target_members=[user.id],
    )


@vc_group.command(name="move", description="指定ユーザーを別のVCチャンネルへ移動します")
async def cmd_vc_move(
    ctx: discord.ApplicationContext,
    user: discord.Member = discord.Option(discord.Member, description="移動するユーザー"),
    channel: discord.VoiceChannel = discord.Option(
        discord.VoiceChannel, description="移動先のVCチャンネル"
    ),
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
        await ctx.respond(
            f"❌ {user.display_name} は {src_channel.mention} にいません", ephemeral=True
        )
        return
    await ctx.respond(f"📤 {user.mention} を {channel.mention} へ移動します")
    try:
        await user.move_to(channel)
    except (discord.Forbidden, discord.HTTPException) as e:
        await ctx.channel.send(f"❌ 移動に失敗しました: {e}")


@vc_group.command(name="move-all", description="現在のVCの全員を別のVCチャンネルへ移動します")
async def cmd_vc_move_all(
    ctx: discord.ApplicationContext,
    channel: discord.VoiceChannel = discord.Option(
        discord.VoiceChannel, description="移動先のVCチャンネル"
    ),
) -> None:
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.respond("❌ まずVCに参加してください", ephemeral=True)
        return
    src_channel = ctx.author.voice.channel
    perms = src_channel.permissions_for(ctx.guild.me)
    if not perms.move_members:
        await ctx.respond("❌ `メンバーを移動` 権限がありません", ephemeral=True)
        return
    all_members = list(src_channel.members)
    bot_members = [m for m in all_members if m.bot and m.id != ctx.guild.me.id]
    human_members = [m for m in all_members if not m.bot]
    if not human_members:
        await ctx.respond(
            f"❌ {src_channel.mention} に移動対象のメンバーがいません", ephemeral=True
        )
        return
    await ctx.respond(
        f"📤 {src_channel.mention} の全員（人間{len(human_members)}人 / Bot{len(bot_members)}体）"
        f"を {channel.mention} へ移動します"
    )
    failed: list[str] = []
    # 他Botを先に移動しておく。人間を先に動かすと、移動先未定のうちに元チャンネルの
    # 人間が0人になり、他Bot側の「人間0人で自動切断」ロジックが新チャンネルへの
    # 追従より先に発火して取り残されてしまう
    for member in bot_members + human_members:
        try:
            await member.move_to(channel)
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.warning("move-all failed for %s: %s", member.display_name, e)
            failed.append(member.display_name)
    if failed:
        await ctx.channel.send(f"⚠️ 移動できなかったメンバー: {', '.join(failed)}")


@bot.event
async def on_ready() -> None:
    logger.info("Bot ready: %s (id=%s)", bot.user, bot.user.id)


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
                    # 実行順序: cancel() → finally → on_complete → _cleanup (stateエントリ削除済み)
                    # cancel()返却後、ローカルstate参照は有効
                if state.voice_client and state.voice_client.is_connected():
                    await state.voice_client.disconnect()
                await state.text_channel.send(
                    f"✅ {state.voice_channel.mention} から全員が退出したため、タイマーを自動キャンセルしました"
                )


token = os.getenv("DISCORD_TOKEN")
if not token:
    raise RuntimeError("DISCORD_TOKEN が設定されていません")

bot.run(token)
