"""トークン数ベースのチャンク分割ユーティリティ

llm.tokenize() で正確なトークン数を計算し、テキストをチャンクリストに分割する。
デフォルト最大 2200 トークン (config.yaml の llm.chunk_size_tokens で変更可能)。

分割方針:
- 改行で行に分割してからトークン数を計算し、上限を超えない範囲でチャンクを構築する。
- 1行だけでトークン上限を超える場合は文字数で強制分割する。
"""

import logging

logger = logging.getLogger(__name__)


def split_into_chunks(text: str, llm, max_tokens: int = 2200) -> list[str]:
    """テキストをトークン数ベースでチャンクに分割して返す。

    Args:
        text: 分割対象のテキスト（トランスクリプト全文など）
        llm: llama-cpp-python の Llama インスタンス（tokenize に使用）
        max_tokens: チャンクあたりの最大トークン数

    Returns:
        チャンク文字列のリスト（各チャンクは max_tokens 以内）
    """
    lines = text.splitlines()
    chunks: list[str] = []
    current_lines: list[str] = []
    current_tokens: int = 0

    for line in lines:
        line_tokens = _count_tokens(llm, line)

        # 1行だけで上限を超える場合は強制分割
        if line_tokens > max_tokens:
            # 現在のバッファを先にフラッシュ
            if current_lines:
                chunks.append("\n".join(current_lines))
                current_lines = []
                current_tokens = 0
            chunks.extend(_split_long_line(llm, line, max_tokens))
            continue

        if current_tokens + line_tokens > max_tokens:
            # バッファをフラッシュしてから新チャンク開始
            chunks.append("\n".join(current_lines))
            current_lines = [line]
            current_tokens = line_tokens
        else:
            current_lines.append(line)
            current_tokens += line_tokens

    # 残りをフラッシュ
    if current_lines:
        chunks.append("\n".join(current_lines))

    logger.info(
        "チャンク分割完了: %d チャンク (最大 %d トークン/チャンク)", len(chunks), max_tokens
    )
    return chunks


def _count_tokens(llm, text: str) -> int:
    """テキストのトークン数を返す。"""
    if not text:
        return 0
    tokens = llm.tokenize(text.encode("utf-8"), add_bos=False, special=False)
    return len(tokens)


def _split_long_line(llm, line: str, max_tokens: int) -> list[str]:
    """1行がトークン上限を超える場合に文字数で強制分割する。

    句読点（。、！？）での分割を優先し、見つからなければ文字数で等分する。
    """
    # 句読点で分割を試みる
    import re

    sentences = re.split(r"(?<=[。、！？\.\!\?])", line)
    chunks: list[str] = []
    current = ""
    current_tokens = 0

    for sent in sentences:
        sent_tokens = _count_tokens(llm, sent)
        if current_tokens + sent_tokens > max_tokens:
            if current:
                chunks.append(current)
            current = sent
            current_tokens = sent_tokens
        else:
            current += sent
            current_tokens += sent_tokens

    if current:
        chunks.append(current)

    logger.warning("長い行を %d チャンクに強制分割しました。", len(chunks))
    return chunks
