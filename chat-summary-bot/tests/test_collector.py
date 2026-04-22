"""collector.py のユニットテスト（動的トランケーション）."""

from collector import CollectResult, _estimate_tokens, _truncate_to_limit


def _make_msg(content: str, idx: int = 0) -> dict:
    return {
        "id": str(idx),
        "channel_id": "ch1",
        "author_name": "Alice",
        "content": content,
        "created_at": 1000 + idx,
    }


def test_estimate_tokens_basic():
    """トークン概算が文字数 // 2 であることを確認する."""
    messages = [_make_msg("あ" * 100)]
    assert _estimate_tokens(messages) == 50


def test_truncate_no_truncation_needed():
    """トークン上限以内ならトランケーションが発生しないことを確認する."""
    # 各メッセージ: 10文字 → 5トークン、10件で50トークン
    msgs = [_make_msg("a" * 10, i) for i in range(10)]
    n_ctx = 8192  # 上限 = 8192 - 3000 = 5192 >> 50トークン
    result, truncated = _truncate_to_limit(msgs, n_ctx)
    assert not truncated
    assert len(result) == 10


def test_truncate_triggers_when_over_limit():
    """トークン上限を超えたらトランケーションが発生することを確認する."""
    # 各メッセージ: 10000文字 → 5000トークン
    # 上限: 8192 - 3000 = 5192トークン → 2件目でオーバー
    msgs = [_make_msg("あ" * 10000, i) for i in range(3)]
    result, truncated = _truncate_to_limit(msgs, n_ctx=8192)
    assert truncated
    assert len(result) < 3


def test_truncate_returns_newer_messages():
    """トランケーション時は先頭（新しい）メッセージが保持されることを確認する."""
    # msgs[0] が最も新しいとして渡す（新しい順）
    msgs = [_make_msg("あ" * 10000, i) for i in range(3)]
    result, truncated = _truncate_to_limit(msgs, n_ctx=8192)
    assert truncated
    # 先頭のメッセージが残っていること
    assert result[0]["id"] == msgs[0]["id"]


def test_collect_result_truncated_flag():
    """CollectResult の truncated フラグが正しく設定されることを確認する."""
    r = CollectResult(messages=[], truncated=True)
    assert r.truncated is True
    r2 = CollectResult(messages=[], truncated=False)
    assert r2.truncated is False
