"""メッセージ収集モジュール（DB優先・Discord APIフォールバック・動的トランケーション）."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import discord

    from db import Database

logger = logging.getLogger(__name__)

# LLM の n_ctx から prompt + output のオーバーヘッドを引いた安全上限
_TOKEN_OVERHEAD = 3000


@dataclass
class CollectResult:
    """メッセージ収集結果."""

    messages: list[dict[str, Any]]
    truncated: bool  # トークン上限で切り詰めが発生した場合 True


def _sort_and_truncate(
    messages: list[dict[str, Any]], n_ctx: int
) -> tuple[list[dict[str, Any]], bool]:
    """新しい順→古い順に並べ直してトークン上限でトランケーションし、古い順で返す."""
    desc = sorted(messages, key=lambda m: m["created_at"], reverse=True)
    kept, truncated = _truncate_to_limit(desc, n_ctx)
    return list(reversed(kept)), truncated


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """日本語対応のトークン数概算（文字数 // 2）."""
    total = sum(len(msg.get("content", "")) for msg in messages)
    return total // 2


def _truncate_to_limit(
    messages: list[dict[str, Any]], n_ctx: int
) -> tuple[list[dict[str, Any]], bool]:
    """トークン上限内に収まるようメッセージを末尾から切り詰める.

    Args:
        messages: 新しい順（降順）のメッセージリスト.
        n_ctx: LLM のコンテキスト長.

    Returns:
        (切り詰め後メッセージリスト, 切り詰めが発生したか).
    """
    limit = n_ctx - _TOKEN_OVERHEAD
    kept = []
    total_tokens = 0
    for msg in messages:
        tokens = len(msg.get("content", "")) // 2
        if total_tokens + tokens > limit:
            return kept, True
        kept.append(msg)
        total_tokens += tokens
    return kept, False


async def fetch_recent(
    db: Database,
    channel: discord.TextChannel,
    limit: int,
    n_ctx: int,
    ttl_days: int,
) -> CollectResult:
    """DB優先でメッセージを取得し、不足分を Discord API で補完する.

    Args:
        db: Database インスタンス.
        channel: Discord テキストチャンネル.
        limit: 取得する最大件数.
        n_ctx: LLM のコンテキスト長（トランケーション用）.
        ttl_days: 新規取得メッセージの TTL（日数）.

    Returns:
        CollectResult（messages は古い順）.
    """
    channel_id = str(channel.id)
    messages = await db.get_messages(channel_id, limit)

    # DB に十分なメッセージがなければ Discord API で補完
    if len(messages) < limit:
        needed = limit - len(messages)
        db_ids = {m["id"] for m in messages}
        try:
            async for discord_msg in channel.history(limit=needed):
                if str(discord_msg.id) not in db_ids and not discord_msg.author.bot:
                    msg_dict = {
                        "id": str(discord_msg.id),
                        "channel_id": channel_id,
                        "author_name": discord_msg.author.display_name,
                        "content": discord_msg.content,
                        "created_at": int(discord_msg.created_at.timestamp()),
                    }
                    messages.append(msg_dict)
                    await db.save_message(
                        msg_dict["id"],
                        channel_id,
                        msg_dict["author_name"],
                        msg_dict["content"],
                        msg_dict["created_at"],
                        ttl_days,
                    )
        except Exception:
            logger.exception("Discord API からのメッセージ取得に失敗しました")

    result_msgs, truncated = _sort_and_truncate(messages, n_ctx)
    if truncated:
        logger.info("トークン上限のため古いメッセージを省略しました")
    return CollectResult(messages=result_msgs, truncated=truncated)


async def fetch_by_topic(
    db: Database,
    query: str,
    limit: int,
    n_ctx: int,
) -> CollectResult:
    """DB の全文検索でトピックに関連するメッセージを取得する.

    Args:
        db: Database インスタンス.
        query: 検索キーワード.
        limit: 取得する最大件数.
        n_ctx: LLM のコンテキスト長（トランケーション用）.

    Returns:
        CollectResult（messages は古い順）.
    """
    messages = await db.search_messages(query, limit)
    result_msgs, truncated = _sort_and_truncate(messages, n_ctx)
    if truncated:
        logger.info("トークン上限のため古いメッセージを省略しました（検索: %s）", query)
    return CollectResult(messages=result_msgs, truncated=truncated)
