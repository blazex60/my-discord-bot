<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-23 | Updated: 2026-04-23 -->

# tests

## Purpose

chat-summary-bot の pytest テストスイート。
LLM 呼び出しはモックで代替し、DB 操作はインメモリ SQLite で実行する。

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | パッケージ初期化（空） |
| `test_collector.py` | `collector.py` のトークン概算・トランケーションロジックのユニットテスト |
| `test_db.py` | `db.py` の SQLite 操作テスト（インメモリ DB） |
| `test_llm_client.py` | `llm_client.py` の HTTP リクエスト・エラーハンドリングテスト（httpx モック） |
| `test_prompts.py` | `prompts.py` のプロンプト組み立てテスト |

## For AI Agents

### Working In This Directory

- テスト実行: `uv run pytest tests/`（chat-summary-bot/ ディレクトリから）
- `llm_client.py` のテストは `httpx` クライアントをモックする（実 LLM サーバーに接続しない）
- DB テストはインメモリ SQLite（`aiosqlite` + `:memory:`）を使用する
- `docker compose up` なしで全テストが通ることを保証する

### Testing Requirements

- 非同期テストは `pytest-asyncio` を使用する（`@pytest.mark.asyncio`）
- `collector.py` の `_estimate_tokens` / `_truncate_to_limit` は純粋関数のため外部依存なしでテスト可能
- `CollectResult` の `truncated` フラグが正しく伝播することを必ずテストする

### Common Patterns

```python
# httpx モックのパターン（test_llm_client.py）
import httpx
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_complete_success():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(200, json={"content": "summary"})
        ...
```

```python
# インメモリ DB のパターン（test_db.py）
from db import Database
import pytest

@pytest.fixture
async def db():
    d = Database(":memory:")
    await d.connect()
    return d
```

## Dependencies

### Internal

- `collector.py`, `db.py`, `llm_client.py`, `prompts.py`（各テストがインポート）

### External

| パッケージ | 用途 |
|---|---|
| `pytest` | テストランナー |
| `pytest-asyncio` | 非同期テストサポート |
| `aiosqlite` | インメモリ SQLite（`":memory:"`） |
| `httpx` | LLM クライアントのモック対象 |

<!-- MANUAL: -->
