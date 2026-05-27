import asyncio
import datetime
import logging
from collections.abc import Awaitable, Callable
from zoneinfo import ZoneInfo

import discord

logger = logging.getLogger(__name__)

JST = ZoneInfo("Asia/Tokyo")


def parse_alarm_time(time_str: str) -> datetime.datetime | None:
    """HH:MM 形式の文字列を UTC aware datetime に変換する。過去の場合は翌日になる。"""
    try:
        parts = time_str.strip().split(":")
        if len(parts) != 2:
            return None
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
    except ValueError:
        return None

    now_jst = datetime.datetime.now(JST)
    trigger_jst = now_jst.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if trigger_jst <= now_jst:
        trigger_jst += datetime.timedelta(days=1)

    return trigger_jst.astimezone(datetime.timezone.utc)


def fmt_jst(dt: datetime.datetime) -> str:
    """UTC aware datetime を JST の HH:MM 表示に変換する。"""
    jst_dt = dt.astimezone(JST)
    return jst_dt.strftime("%Y-%m-%d %H:%M JST")


class GuildTimer:
    def __init__(
        self,
        voice_client: discord.VoiceClient | None,
        voice_channel: discord.VoiceChannel,
        text_channel: discord.TextChannel,
        trigger_at: datetime.datetime,
        warning_seconds: int,
        on_complete: Callable[[], Awaitable[None]],
        target_members: list[int] | None = None,
    ) -> None:
        self._voice_client = voice_client
        self._voice_channel = voice_channel
        self._text_channel = text_channel
        self._trigger_at = trigger_at
        self._warning_seconds = warning_seconds
        self._on_complete = on_complete
        self._target_members = target_members
        self._task: asyncio.Task | None = None

    def start(self) -> asyncio.Task:
        self._task = asyncio.create_task(self._run())
        return self._task

    async def cancel(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def seconds_remaining(self) -> float:
        now = datetime.datetime.now(datetime.timezone.utc)
        remaining = (self._trigger_at - now).total_seconds()
        return max(0.0, remaining)

    async def _run(self) -> None:
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            total_seconds = (self._trigger_at - now).total_seconds()

            if total_seconds <= 0:
                await self._disconnect_all()
                return

            warning_wait = total_seconds - self._warning_seconds
            if warning_wait > 0:
                await asyncio.sleep(warning_wait)
                if self._target_members is not None:
                    target_label = f"{len(self._target_members)}人の指定メンバーを切断します"
                else:
                    target_label = f"{self._voice_channel.mention} の全員を切断します"
                await self._text_channel.send(f"⚠️ あと{self._warning_seconds}秒で {target_label}")
                await asyncio.sleep(self._warning_seconds)
            else:
                await asyncio.sleep(total_seconds)

            await self._disconnect_all()

        except asyncio.CancelledError:
            logger.info("GuildTimer cancelled (channel=%s)", self._voice_channel.id)
            raise
        finally:
            await self._on_complete()

    async def _disconnect_all(self) -> None:
        channel = self._voice_channel
        perms = channel.permissions_for(channel.guild.me)

        if not perms.move_members:
            await self._text_channel.send(
                f"❌ `メンバーを移動` 権限がないため {channel.mention} の全員を切断できません"
            )
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
            await self._text_channel.send(f"ℹ️ 対象メンバーは既に {channel.mention} にいません")
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
