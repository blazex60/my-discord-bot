"""SQLite データベース操作モジュール（aiosqlite + TTL管理）."""

import time
from pathlib import Path
from typing import Any

import aiosqlite


class Database:
    """aiosqlite ラッパー。メッセージキャッシュと設定を管理する."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """データベース接続を確立し、テーブルを初期化する."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self.init_db()

    async def close(self) -> None:
        """データベース接続を閉じる."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def init_db(self) -> None:
        """テーブルを作成する（存在しない場合のみ）."""
        assert self._conn is not None
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id          TEXT PRIMARY KEY,
                channel_id  TEXT NOT NULL,
                author_name TEXT NOT NULL,
                content     TEXT NOT NULL,
                created_at  INTEGER NOT NULL,
                expires_at  INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages(channel_id);
            CREATE INDEX IF NOT EXISTS idx_messages_expires ON messages(expires_at);

            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        await self._conn.commit()

    async def save_message(
        self,
        msg_id: str,
        channel_id: str,
        author_name: str,
        content: str,
        created_at: int,
        ttl_days: int = 30,
    ) -> None:
        """メッセージを保存する. ttl_days 後に期限切れとなる."""
        assert self._conn is not None
        expires_at = int(time.time()) + ttl_days * 86400
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO messages
                (id, channel_id, author_name, content, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (msg_id, channel_id, author_name, content, created_at, expires_at),
        )
        await self._conn.commit()

    async def get_messages(self, channel_id: str, limit: int = 80) -> list[dict[str, Any]]:
        """チャンネルIDで有効なメッセージを新しい順に取得する."""
        assert self._conn is not None
        now = int(time.time())
        async with self._conn.execute(
            """
            SELECT id, channel_id, author_name, content, created_at
            FROM messages
            WHERE channel_id = ? AND expires_at > ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (channel_id, now, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "channel_id": r[1],
                "author_name": r[2],
                "content": r[3],
                "created_at": r[4],
            }
            for r in rows
        ]

    async def search_messages(self, query: str, limit: int = 80) -> list[dict[str, Any]]:
        """全チャンネルのメッセージをコンテンツで部分一致検索する."""
        assert self._conn is not None
        now = int(time.time())
        async with self._conn.execute(
            """
            SELECT id, channel_id, author_name, content, created_at
            FROM messages
            WHERE content LIKE ? AND expires_at > ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (f"%{query}%", now, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "channel_id": r[1],
                "author_name": r[2],
                "content": r[3],
                "created_at": r[4],
            }
            for r in rows
        ]

    async def delete_expired(self) -> int:
        """期限切れメッセージを削除し、削除件数を返す."""
        assert self._conn is not None
        now = int(time.time())
        cursor = await self._conn.execute("DELETE FROM messages WHERE expires_at <= ?", (now,))
        await self._conn.commit()
        return cursor.rowcount

    async def get_config(self, key: str, default: str | None = None) -> str | None:
        """設定値を取得する. 存在しない場合は default を返す."""
        assert self._conn is not None
        async with self._conn.execute("SELECT value FROM config WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else default

    async def set_config(self, key: str, value: str) -> None:
        """設定値を保存する."""
        assert self._conn is not None
        await self._conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            (key, value),
        )
        await self._conn.commit()

    async def delete_config(self, key: str) -> None:
        """設定値を削除する."""
        assert self._conn is not None
        await self._conn.execute("DELETE FROM config WHERE key = ?", (key,))
        await self._conn.commit()
