"""LLM プロンプト定義モジュール."""

from typing import Any


def _format_messages(messages: list[dict[str, Any]]) -> str:
    """メッセージリストを会話形式のテキストに変換する."""
    lines = []
    for msg in messages:
        author = msg.get("author_name", "不明")
        content = msg.get("content", "")
        lines.append(f"{author}: {content}")
    return "\n".join(lines)


def build_summary_prompt(messages: list[dict[str, Any]]) -> str:
    """要約プロンプトを構築する."""
    conversation = _format_messages(messages)
    return f"""あなたはDiscordサーバーの会話を要約するアシスタントです。
以下の会話を日本語で箇条書きにまとめてください。
話題ごとにグループ化し、各項目は「・」で始めてください。
固有名詞や重要な情報はそのまま残してください。

---
{conversation}
---

上記の会話の要約（日本語・箇条書き）:"""


def build_search_prompt(messages: list[dict[str, Any]], query: str) -> str:
    """検索・関連抽出プロンプトを構築する."""
    conversation = _format_messages(messages)
    return f"""あなたはDiscordサーバーの会話から関連情報を抽出するアシスタントです。
以下の会話から「{query}」に関連する内容を抽出し、日本語で箇条書きにまとめてください。
関係のない部分は省略してください。各項目は「・」で始めてください。

---
{conversation}
---

「{query}」に関連する内容の要約（日本語・箇条書き）:"""


def build_catchup_prompt(messages: list[dict[str, Any]], topic: str) -> str:
    """追いつき要約プロンプトを構築する."""
    conversation = _format_messages(messages)
    return f"""あなたはDiscordサーバーの会話を要約するアシスタントです。
以下の会話における「{topic}」に関する話題の流れを、時系列で日本語の箇条書きにまとめてください。
誰が何を言ったかの流れが分かるようにしてください。各項目は「・」で始めてください。

---
{conversation}
---

「{topic}」の話題の流れ（日本語・箇条書き）:"""
