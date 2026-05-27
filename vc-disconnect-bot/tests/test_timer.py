import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from timer import GuildTimer, fmt_jst, parse_alarm_time


# --- parse_alarm_time ---


def test_parse_alarm_time_valid_future():
    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    jst = ZoneInfo("Asia/Tokyo")
    future_jst = future.astimezone(jst)
    time_str = future_jst.strftime("%H:%M")

    result = parse_alarm_time(time_str)

    assert result is not None
    assert result.tzinfo == datetime.timezone.utc
    assert result > datetime.datetime.now(datetime.timezone.utc)


def test_parse_alarm_time_past_pushes_to_tomorrow():
    past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    jst = ZoneInfo("Asia/Tokyo")
    past_jst = past.astimezone(jst)
    time_str = past_jst.strftime("%H:%M")

    result = parse_alarm_time(time_str)

    assert result is not None
    assert result > datetime.datetime.now(datetime.timezone.utc)
    delta = result - datetime.datetime.now(datetime.timezone.utc)
    assert delta.total_seconds() < 86400 + 60


def test_parse_alarm_time_invalid_format():
    assert parse_alarm_time("25:00") is None
    assert parse_alarm_time("12:60") is None
    assert parse_alarm_time("abc") is None
    assert parse_alarm_time("12") is None
    assert parse_alarm_time("12:00:00") is None


def test_parse_alarm_time_boundary():
    assert parse_alarm_time("00:00") is not None
    assert parse_alarm_time("23:59") is not None


# --- fmt_jst ---


def test_fmt_jst():
    utc_dt = datetime.datetime(2026, 5, 23, 13, 0, 0, tzinfo=datetime.timezone.utc)
    result = fmt_jst(utc_dt)
    assert "2026-05-23" in result
    assert "22:00 JST" in result


# --- GuildTimer helpers ---


def _make_member(display_name: str, is_bot: bool = False) -> MagicMock:
    member = MagicMock()
    member.display_name = display_name
    member.bot = is_bot
    member.move_to = AsyncMock()
    return member


def _make_timer(trigger_at, warning_seconds=60, on_complete=None, members=None):
    voice_client = MagicMock(spec=["is_connected", "disconnect"])
    voice_client.is_connected.return_value = True
    voice_client.disconnect = AsyncMock()

    perms = MagicMock()
    perms.move_members = True

    voice_channel = MagicMock(spec=["id", "mention", "members", "guild", "permissions_for"])
    voice_channel.id = 123
    voice_channel.mention = "#vc"
    voice_channel.members = members if members is not None else []
    voice_channel.guild = MagicMock()
    voice_channel.permissions_for = MagicMock(return_value=perms)

    text_channel = MagicMock(spec=["send"])
    text_channel.send = AsyncMock()

    if on_complete is None:
        on_complete = AsyncMock()

    return GuildTimer(
        voice_client=voice_client,
        voice_channel=voice_channel,
        text_channel=text_channel,
        trigger_at=trigger_at,
        warning_seconds=warning_seconds,
        on_complete=on_complete,
    )


# --- GuildTimer tests ---


def test_seconds_remaining_future():
    trigger_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=120)
    timer = _make_timer(trigger_at)
    remaining = timer.seconds_remaining()
    assert 118 < remaining <= 120


def test_seconds_remaining_past():
    trigger_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10)
    timer = _make_timer(trigger_at)
    assert timer.seconds_remaining() == 0.0


@pytest.mark.asyncio
async def test_timer_fires_immediately_when_past():
    trigger_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
    on_complete = AsyncMock()
    timer = _make_timer(trigger_at, on_complete=on_complete)

    task = timer.start()
    await asyncio.wait_for(task, timeout=2.0)

    timer._text_channel.send.assert_called()
    on_complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_timer_cancel_stops_cleanly():
    trigger_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=300)
    on_complete = AsyncMock()
    timer = _make_timer(trigger_at, on_complete=on_complete)

    timer.start()
    await asyncio.sleep(0.05)
    await timer.cancel()

    on_complete.assert_awaited_once()
    timer._text_channel.send.assert_not_called()


@pytest.mark.asyncio
async def test_disconnect_all_moves_human_members_only():
    """Bot メンバーは move_to(None) せず、人間メンバーのみ切断する。"""
    trigger_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
    on_complete = AsyncMock()

    human1 = _make_member("Alice")
    human2 = _make_member("Bob")
    bot_member = _make_member("MusicBot", is_bot=True)

    timer = _make_timer(
        trigger_at, warning_seconds=0, on_complete=on_complete, members=[human1, human2, bot_member]
    )

    task = timer.start()
    await asyncio.wait_for(task, timeout=2.0)

    human1.move_to.assert_awaited_once_with(None)
    human2.move_to.assert_awaited_once_with(None)
    bot_member.move_to.assert_not_called()
    timer._voice_client.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_disconnect_all_no_move_members_permission():
    trigger_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
    on_complete = AsyncMock()
    timer = _make_timer(trigger_at, on_complete=on_complete)

    perms = MagicMock()
    perms.move_members = False
    timer._voice_channel.permissions_for.return_value = perms

    member = _make_member("Alice")
    timer._voice_channel.members = [member]

    task = timer.start()
    await asyncio.wait_for(task, timeout=2.0)

    member.move_to.assert_not_called()
    timer._voice_client.disconnect.assert_awaited_once()
    timer._text_channel.send.assert_called()
    assert any("権限" in str(c) for c in timer._text_channel.send.call_args_list)
