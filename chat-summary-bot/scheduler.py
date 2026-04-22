"""定期自動投稿スケジューラ（APScheduler + DB永続化）."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    from db import Database

logger = logging.getLogger(__name__)

_CONFIG_KEY_CRON = "autopost_cron"
_CONFIG_KEY_CHANNEL = "autopost_channel_id"
JOB_ID = "autopost"


class AutoPostScheduler:
    """定期投稿の開始・停止・永続化を管理する."""

    def __init__(
        self, db: Database, post_callback: Callable[[int], Coroutine[Any, Any, None]]
    ) -> None:
        """
        Args:
            db: Database インスタンス（設定の永続化に使用）.
            post_callback: 投稿先チャンネルIDを受け取る非同期コールバック.
        """
        self._db = db
        self._callback = post_callback
        self._scheduler = AsyncIOScheduler()

    def start(self) -> None:
        """スケジューラを起動する."""
        self._scheduler.start()
        logger.info("スケジューラ起動")

    def stop(self) -> None:
        """スケジューラを停止する."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        logger.info("スケジューラ停止")

    async def restore_from_db(self) -> bool:
        """DB から自動投稿設定を読み込んでジョブを復元する.

        Returns:
            設定が復元された場合 True.
        """
        cron = await self._db.get_config(_CONFIG_KEY_CRON)
        channel_id_str = await self._db.get_config(_CONFIG_KEY_CHANNEL)
        if cron and channel_id_str:
            self._add_job(cron, int(channel_id_str))
            logger.info("自動投稿設定を復元: cron=%s channel=%s", cron, channel_id_str)
            return True
        return False

    async def start_autopost(self, cron_expr: str, channel_id: int) -> None:
        """自動投稿スケジュールを設定して DB に永続化する.

        Args:
            cron_expr: cron 形式の文字列（例: "0 9 * * *"）.
            channel_id: 投稿先の Discord チャンネル ID.
        """
        self._remove_existing_job()
        self._add_job(cron_expr, channel_id)
        await self._db.set_config(_CONFIG_KEY_CRON, cron_expr)
        await self._db.set_config(_CONFIG_KEY_CHANNEL, str(channel_id))
        logger.info("自動投稿設定: cron=%s channel=%s", cron_expr, channel_id)

    async def stop_autopost(self) -> None:
        """自動投稿を停止して DB の設定を削除する."""
        self._remove_existing_job()
        await self._db.delete_config(_CONFIG_KEY_CRON)
        await self._db.delete_config(_CONFIG_KEY_CHANNEL)
        logger.info("自動投稿停止")

    def is_active(self) -> bool:
        """自動投稿ジョブが登録されているか確認する."""
        return self._scheduler.get_job(JOB_ID) is not None

    def _add_job(self, cron_expr: str, channel_id: int) -> None:
        parts = cron_expr.split()
        if len(parts) != 5:
            raise ValueError(f"不正な cron 式: {cron_expr!r}（'分 時 日 月 曜' の形式で指定）")
        minute, hour, day, month, day_of_week = parts
        self._scheduler.add_job(
            self._callback,
            CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
            ),
            args=[channel_id],
            id=JOB_ID,
            replace_existing=True,
        )

    def _remove_existing_job(self) -> None:
        if self._scheduler.get_job(JOB_ID):
            self._scheduler.remove_job(JOB_ID)
