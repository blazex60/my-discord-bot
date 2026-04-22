"""db.py のユニットテスト（インメモリ SQLite）."""

import time

import pytest

from db import Database


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.connect()
    yield database
    await database.close()


async def test_init_db_creates_tables(db):
    """init_db がテーブルを作成することを確認する."""
    # テーブルが存在するか（エラーなしで操作できれば OK）
    result = await db.get_messages("ch1", 10)
    assert result == []


async def test_save_and_get_message(db):
    """save_message と get_messages が正しく動作することを確認する."""
    now = int(time.time())
    await db.save_message("msg1", "ch1", "Alice", "こんにちは", now, ttl_days=30)
    messages = await db.get_messages("ch1", 10)
    assert len(messages) == 1
    assert messages[0]["author_name"] == "Alice"
    assert messages[0]["content"] == "こんにちは"


async def test_get_messages_channel_isolation(db):
    """チャンネルIDが異なるメッセージが混在しないことを確認する."""
    now = int(time.time())
    await db.save_message("msg1", "ch1", "Alice", "ch1のメッセージ", now, 30)
    await db.save_message("msg2", "ch2", "Bob", "ch2のメッセージ", now, 30)
    ch1_msgs = await db.get_messages("ch1", 10)
    assert len(ch1_msgs) == 1
    assert ch1_msgs[0]["channel_id"] == "ch1"


async def test_ttl_expired_message_not_returned(db):
    """TTL が切れたメッセージは get_messages で返されないことを確認する."""
    past = int(time.time()) - 100
    # expires_at が過去になるよう ttl_days=0 相当の直接挿入
    await db._conn.execute(
        "INSERT INTO messages (id, channel_id, author_name, content, created_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("msg_old", "ch1", "Alice", "古いメッセージ", past, past - 1),
    )
    await db._conn.commit()
    messages = await db.get_messages("ch1", 10)
    assert all(m["id"] != "msg_old" for m in messages)


async def test_delete_expired(db):
    """delete_expired が TTL 切れメッセージを削除することを確認する."""
    past = int(time.time()) - 100
    await db._conn.execute(
        "INSERT INTO messages (id, channel_id, author_name, content, created_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("msg_expire", "ch1", "Alice", "期限切れ", past, past - 1),
    )
    await db._conn.commit()
    deleted = await db.delete_expired()
    assert deleted >= 1


async def test_search_messages(db):
    """search_messages がコンテンツの部分一致で検索できることを確認する."""
    now = int(time.time())
    await db.save_message("msg1", "ch1", "Alice", "アニメの話をしよう", now, 30)
    await db.save_message("msg2", "ch1", "Bob", "ゲームの話をしよう", now, 30)
    results = await db.search_messages("アニメ", 10)
    assert len(results) == 1
    assert results[0]["content"] == "アニメの話をしよう"


async def test_config_crud(db):
    """get_config / set_config / delete_config が正しく動作することを確認する."""
    assert await db.get_config("test_key") is None
    assert await db.get_config("test_key", "default") == "default"
    await db.set_config("test_key", "test_value")
    assert await db.get_config("test_key") == "test_value"
    await db.delete_config("test_key")
    assert await db.get_config("test_key") is None
