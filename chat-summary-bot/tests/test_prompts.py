"""prompts.py のユニットテスト."""

from prompts import build_catchup_prompt, build_search_prompt, build_summary_prompt

_SAMPLE_MESSAGES = [
    {"author_name": "Alice", "content": "アニメ見てる？"},
    {"author_name": "Bob", "content": "ダンダダン最高だよ"},
]


def test_build_summary_prompt_returns_string():
    """build_summary_prompt が文字列を返すことを確認する."""
    result = build_summary_prompt(_SAMPLE_MESSAGES)
    assert isinstance(result, str)
    assert len(result) > 0


def test_build_summary_prompt_contains_messages():
    """build_summary_prompt がメッセージの内容を含むことを確認する."""
    result = build_summary_prompt(_SAMPLE_MESSAGES)
    assert "Alice" in result
    assert "ダンダダン" in result


def test_build_search_prompt_returns_string():
    """build_search_prompt が文字列を返すことを確認する."""
    result = build_search_prompt(_SAMPLE_MESSAGES, "アニメ")
    assert isinstance(result, str)
    assert len(result) > 0


def test_build_search_prompt_contains_query():
    """build_search_prompt がクエリを含むことを確認する."""
    result = build_search_prompt(_SAMPLE_MESSAGES, "アニメ")
    assert "アニメ" in result


def test_build_catchup_prompt_returns_string():
    """build_catchup_prompt が文字列を返すことを確認する."""
    result = build_catchup_prompt(_SAMPLE_MESSAGES, "ゲーム")
    assert isinstance(result, str)
    assert len(result) > 0


def test_build_catchup_prompt_contains_topic():
    """build_catchup_prompt がトピックを含むことを確認する."""
    result = build_catchup_prompt(_SAMPLE_MESSAGES, "ゲーム")
    assert "ゲーム" in result


def test_prompts_include_japanese_instruction():
    """各プロンプトが日本語出力を指示する文字列を含むことを確認する."""
    for prompt in [
        build_summary_prompt(_SAMPLE_MESSAGES),
        build_search_prompt(_SAMPLE_MESSAGES, "test"),
        build_catchup_prompt(_SAMPLE_MESSAGES, "test"),
    ]:
        assert "日本語" in prompt
