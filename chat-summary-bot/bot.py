"""Discord チャット要約 Bot エントリーポイント."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

import discord
import yaml
from dotenv import load_dotenv

from collector import fetch_by_topic, fetch_recent
from db import Database
from llm_client import LLMClient, LLMUnavailableError
from prompts import build_catchup_prompt, build_search_prompt, build_summary_prompt
from scheduler import AutoPostScheduler

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── 設定読み込み ────────────────────────────────────────────────
_CONFIG_PATH = Path(__file__).parent / "config.yaml"
with _CONFIG_PATH.open() as f:
    _CONFIG = yaml.safe_load(f)

_LLM_URL = os.getenv("LLM_URL", _CONFIG["llm"]["url"])
_DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
_DB_PATH = _CONFIG["storage"]["db_path"]
_TTL_DAYS = int(_CONFIG["storage"]["ttl_days"])
_MAX_MSGS = int(_CONFIG["storage"]["max_messages_per_query"])
_N_CTX = int(_CONFIG["llm"]["n_ctx"])
_LLM_TIMEOUT = float(_CONFIG["llm"]["timeout_seconds"])
_LLM_MAX_TOKENS = int(_CONFIG["llm"]["max_tokens"])

# ── Discord Bot 設定 ────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Bot(intents=intents)

db = Database(_DB_PATH)
llm = LLMClient(_LLM_URL, _LLM_TIMEOUT, _LLM_MAX_TOKENS)
scheduler: AutoPostScheduler | None = None

_EXCLUDED_KEY = "excluded_channels"


async def _get_excluded_channels_async() -> set[int]:
    raw = await db.get_config(_EXCLUDED_KEY)
    if not raw:
        return set()
    try:
        return set(json.loads(raw))
    except json.JSONDecodeError:
        return set()


async def _set_excluded_channels(channels: set[int]) -> None:
    await db.set_config(_EXCLUDED_KEY, json.dumps(list(channels)))


def _truncation_note(truncated: bool) -> str:
    return "\n> （古いメッセージは省略しました）" if truncated else ""


async def _autopost_callback(channel_id: int) -> None:
    """定期投稿コールバック."""
    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        logger.warning("自動投稿先チャンネル %s が見つかりません", channel_id)
        return
    try:
        result = await fetch_recent(db, channel, _MAX_MSGS, _N_CTX, _TTL_DAYS)
        if not result.messages:
            return
        prompt = build_summary_prompt(result.messages)
        summary = await llm.complete(prompt)
        note = _truncation_note(result.truncated)
        await channel.send(f"📝 **定期まとめ**\n{summary}{note}")
    except LLMUnavailableError as e:
        await channel.send(f"❌ LLM エラー: {e}")


async def _ttl_cleanup_task() -> None:
    """TTL 切れメッセージを定期削除するバックグラウンドタスク."""
    while True:
        try:
            deleted = await db.delete_expired()
            if deleted:
                logger.info("TTL切れメッセージを %d 件削除しました", deleted)
        except Exception:
            logger.exception("TTLクリーンアップに失敗しました")
        await asyncio.sleep(3600)  # 1時間ごと


# ── イベントハンドラ ─────────────────────────────────────────────
@bot.event
async def on_ready() -> None:
    global scheduler
    await db.connect()
    asyncio.create_task(_ttl_cleanup_task())
    scheduler = AutoPostScheduler(db, _autopost_callback)
    scheduler.start()
    await scheduler.restore_from_db()
    logger.info("Bot 起動完了: %s", bot.user)


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return
    if not isinstance(message.channel, discord.TextChannel):
        return
    excluded = await _get_excluded_channels_async()
    if message.channel.id in excluded:
        return
    await db.save_message(
        str(message.id),
        str(message.channel.id),
        message.author.display_name,
        message.content,
        int(message.created_at.timestamp()),
        _TTL_DAYS,
    )


# ── スラッシュコマンド ───────────────────────────────────────────
@bot.slash_command(name="summary", description="直近のメッセージを箇条書きで要約します")
async def cmd_summary(
    ctx: discord.ApplicationContext,
    count: discord.Option(
        int, "取得件数（デフォルト50）", default=50, min_value=1, max_value=_MAX_MSGS
    ),
) -> None:
    await ctx.defer()
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.respond("❌ テキストチャンネルでのみ使用できます")
        return
    try:
        result = await fetch_recent(db, ctx.channel, count, _N_CTX, _TTL_DAYS)
        if not result.messages:
            await ctx.respond("📭 メッセージが見つかりませんでした")
            return
        prompt = build_summary_prompt(result.messages)
        summary = await llm.complete(prompt)
        note = _truncation_note(result.truncated)
        await ctx.respond(f"📝 **要約**\n{summary}{note}")
    except LLMUnavailableError as e:
        await ctx.respond(f"❌ LLM エラー: {e}")


@bot.slash_command(name="search", description="キーワードに関連する会話を検索・要約します")
async def cmd_search(
    ctx: discord.ApplicationContext,
    query: discord.Option(str, "検索キーワード"),
) -> None:
    await ctx.defer()
    try:
        result = await fetch_by_topic(db, query, _MAX_MSGS, _N_CTX)
        if not result.messages:
            await ctx.respond(f"🔍 「{query}」に関連するメッセージが見つかりませんでした")
            return
        prompt = build_search_prompt(result.messages, query)
        summary = await llm.complete(prompt)
        # Discord メッセージリンクを生成
        links = []
        guild_id = ctx.guild_id
        for msg in result.messages[:5]:
            channel_id = msg["channel_id"]
            msg_id = msg["id"]
            links.append(f"https://discord.com/channels/{guild_id}/{channel_id}/{msg_id}")
        link_text = "\n".join(f"• {link}" for link in links) if links else ""
        note = _truncation_note(result.truncated)
        response = f"🔍 **「{query}」の検索結果**\n{summary}{note}"
        if link_text:
            response += f"\n\n**関連メッセージ:**\n{link_text}"
        await ctx.respond(response)
    except LLMUnavailableError as e:
        await ctx.respond(f"❌ LLM エラー: {e}")


@bot.slash_command(name="catch_up", description="特定の話題の流れを追いつき要約します")
async def cmd_catch_up(
    ctx: discord.ApplicationContext,
    topic: discord.Option(str, "追いつきたい話題"),
) -> None:
    await ctx.defer()
    try:
        result = await fetch_by_topic(db, topic, _MAX_MSGS, _N_CTX)
        if not result.messages:
            await ctx.respond(f"📭 「{topic}」に関するメッセージが見つかりませんでした")
            return
        prompt = build_catchup_prompt(result.messages, topic)
        summary = await llm.complete(prompt)
        note = _truncation_note(result.truncated)
        await ctx.respond(f"📖 **「{topic}」の流れ**\n{summary}{note}")
    except LLMUnavailableError as e:
        await ctx.respond(f"❌ LLM エラー: {e}")


watch_group = bot.create_group("watch", "監視チャンネルの管理")


@watch_group.command(name="add", description="チャンネルを監視除外リストに追加します")
async def cmd_watch_add(
    ctx: discord.ApplicationContext,
    channel: discord.Option(discord.TextChannel, "除外するチャンネル"),
) -> None:
    excluded = await _get_excluded_channels_async()
    excluded.add(channel.id)
    await _set_excluded_channels(excluded)
    await ctx.respond(f"✅ {channel.mention} を監視除外リストに追加しました")


@watch_group.command(name="remove", description="チャンネルを監視除外リストから削除します")
async def cmd_watch_remove(
    ctx: discord.ApplicationContext,
    channel: discord.Option(discord.TextChannel, "除外を解除するチャンネル"),
) -> None:
    excluded = await _get_excluded_channels_async()
    excluded.discard(channel.id)
    await _set_excluded_channels(excluded)
    await ctx.respond(f"✅ {channel.mention} の監視を再開しました")


autopost_group = bot.create_group("autopost", "定期自動投稿の管理")


@autopost_group.command(name="set", description="定期投稿スケジュールを設定します")
async def cmd_autopost_set(
    ctx: discord.ApplicationContext,
    cron: discord.Option(str, "cron 式（例: 0 9 * * *）"),
    channel: discord.Option(discord.TextChannel, "投稿先チャンネル", default=None),
) -> None:
    target = channel or ctx.channel
    if not isinstance(target, discord.TextChannel):
        await ctx.respond("❌ テキストチャンネルを指定してください")
        return
    try:
        assert scheduler is not None
        await scheduler.start_autopost(cron, target.id)
        await ctx.respond(
            f"✅ 定期投稿を設定しました\n• cron: `{cron}`\n• チャンネル: {target.mention}"
        )
    except ValueError as e:
        await ctx.respond(f"❌ {e}")


@autopost_group.command(name="off", description="定期自動投稿を停止します")
async def cmd_autopost_off(ctx: discord.ApplicationContext) -> None:
    assert scheduler is not None
    await scheduler.stop_autopost()
    await ctx.respond("✅ 定期投稿を停止しました")


if __name__ == "__main__":
    if not _DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN が設定されていません。.env ファイルを確認してください。")
    bot.run(_DISCORD_TOKEN)
