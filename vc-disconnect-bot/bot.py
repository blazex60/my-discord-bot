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
    voice_client: discord.VoiceClient
    voice_channel: discord.VoiceChannel
    text_channel: discord.TextChannel
    task: asyncio.Task
    timer: GuildTimer
    mode: str
    trigger_at: datetime.datetime


_guild_states: dict[int, GuildState] = {}


async def _cleanup(guild_id: int) -> None:
    _guild_states.pop(guild_id, None)


async def _ensure_joined(
    ctx: discord.ApplicationContext,
) -> tuple[discord.VoiceClient | None, discord.VoiceChannel | None]:
    guild_id = ctx.guild_id

    if guild_id in _guild_states:
        state = _guild_states[guild_id]
        if not state.task.done():
            await ctx.respond(
                "❌ すでにタイマーが動いています。`/vc cancel` で先にキャンセルしてください",
                ephemeral=True,
            )
            return None, None
        return state.voice_client, state.voice_channel

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.respond("❌ まずVCに参加してください", ephemeral=True)
        return None, None

    channel = ctx.author.voice.channel
    perms = channel.permissions_for(ctx.guild.me)
    if not perms.connect:
        await ctx.respond(f"❌ {channel.mention} に接続する権限がありません", ephemeral=True)
        return None, None

    voice_client = await channel.connect()
    return voice_client, channel


async def _arm_timer(
    ctx: discord.ApplicationContext,
    voice_client: discord.VoiceClient,
    voice_channel: discord.VoiceChannel,
    trigger_at: datetime.datetime,
    mode: str,
) -> None:
    guild_id = ctx.guild_id

    async def on_complete() -> None:
        await _cleanup(guild_id)

    timer = GuildTimer(
        voice_client=voice_client,
        voice_channel=voice_channel,
        text_channel=ctx.channel,
        trigger_at=trigger_at,
        warning_seconds=_WARNING_SECONDS,
        on_complete=on_complete,
    )
    task = timer.start()

    _guild_states[guild_id] = GuildState(
        voice_client=voice_client,
        voice_channel=voice_channel,
        text_channel=ctx.channel,
        task=task,
        timer=timer,
        mode=mode,
        trigger_at=trigger_at,
    )


@vc_group.command(name="join", description="ボットを現在のVCに参加させます（タイマーなし）")
async def cmd_vc_join(ctx: discord.ApplicationContext) -> None:
    if ctx.guild_id in _guild_states:
        state = _guild_states[ctx.guild_id]
        await ctx.respond(
            f"❌ すでに {state.voice_channel.mention} に参加しています", ephemeral=True
        )
        return

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.respond("❌ まずVCに参加してください", ephemeral=True)
        return

    channel = ctx.author.voice.channel
    perms = channel.permissions_for(ctx.guild.me)
    if not perms.connect:
        await ctx.respond(f"❌ {channel.mention} に接続する権限がありません", ephemeral=True)
        return

    voice_client = await channel.connect()

    async def on_complete() -> None:
        await _cleanup(ctx.guild_id)

    timer_placeholder = GuildTimer(
        voice_client=voice_client,
        voice_channel=channel,
        text_channel=ctx.channel,
        trigger_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365),
        warning_seconds=_WARNING_SECONDS,
        on_complete=on_complete,
    )

    _guild_states[ctx.guild_id] = GuildState(
        voice_client=voice_client,
        voice_channel=channel,
        text_channel=ctx.channel,
        task=asyncio.get_event_loop().create_future(),
        timer=timer_placeholder,
        mode="none",
        trigger_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365),
    )
    _guild_states[ctx.guild_id].task.cancel()

    await ctx.respond(
        f"✅ {channel.mention} に参加しました。`/vc timer` または `/vc alarm` でタイマーを設定してください"
    )


@vc_group.command(name="timer", description="N分後にVCの全員を切断します")
async def cmd_vc_timer(
    ctx: discord.ApplicationContext,
    minutes: int = discord.Option(int, description="切断までの分数（1〜1440）", min_value=1, max_value=1440),
) -> None:
    voice_client, voice_channel = await _ensure_joined(ctx)
    if voice_client is None:
        return

    trigger_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)
    await _arm_timer(ctx, voice_client, voice_channel, trigger_at, mode="timer")
    await ctx.respond(
        f"⏱️ {minutes}分後（{fmt_jst(trigger_at)}）に {voice_channel.mention} の全員を切断します"
    )


@vc_group.command(name="alarm", description="指定時刻（JST）にVCの全員を切断します")
async def cmd_vc_alarm(
    ctx: discord.ApplicationContext,
    time: str = discord.Option(str, description="切断時刻 HH:MM（例: 22:00）"),
) -> None:
    trigger_at = parse_alarm_time(time)
    if trigger_at is None:
        await ctx.respond(
            "❌ 時刻の形式が正しくありません（例: 22:00）", ephemeral=True
        )
        return

    voice_client, voice_channel = await _ensure_joined(ctx)
    if voice_client is None:
        return

    await _arm_timer(ctx, voice_client, voice_channel, trigger_at, mode="alarm")
    await ctx.respond(
        f"⏰ {fmt_jst(trigger_at)} に {voice_channel.mention} の全員を切断します"
    )


@vc_group.command(name="status", description="現在のタイマー状態を表示します")
async def cmd_vc_status(ctx: discord.ApplicationContext) -> None:
    state = _guild_states.get(ctx.guild_id)
    if not state or state.mode == "none":
        await ctx.respond("📭 現在アクティブなタイマーはありません", ephemeral=True)
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

    mode_label = "タイマー" if state.mode == "timer" else "アラーム"
    await ctx.respond(
        f"📊 **VC切断タイマー**\n"
        f"• チャンネル: {state.voice_channel.mention}\n"
        f"• モード: {mode_label}\n"
        f"• 切断予定: {fmt_jst(state.trigger_at)}\n"
        f"• 残り: {remaining_str}"
    )


@vc_group.command(name="cancel", description="タイマーをキャンセルしてVCから退出します")
async def cmd_vc_cancel(ctx: discord.ApplicationContext) -> None:
    state = _guild_states.pop(ctx.guild_id, None)
    if not state:
        await ctx.respond("📭 キャンセルするタイマーがありません", ephemeral=True)
        return

    await state.timer.cancel()
    if state.voice_client.is_connected():
        await state.voice_client.disconnect()

    await ctx.respond(
        f"✅ タイマーをキャンセルしました。{state.voice_channel.mention} から退出しました"
    )


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
    state = _guild_states.get(guild_id)
    if not state:
        return

    if before.channel == state.voice_channel and after.channel != state.voice_channel:
        human_members = [m for m in state.voice_channel.members if not m.bot]
        if not human_members and state.mode != "none":
            logger.info(
                "All humans left %s, timer still running (will fire at %s)",
                state.voice_channel.name,
                state.trigger_at,
            )


token = os.getenv("DISCORD_TOKEN")
if not token:
    raise RuntimeError("DISCORD_TOKEN が設定されていません")

bot.run(token)
