"""llm_client.py のユニットテスト（httpx モック）."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from llm_client import LLMClient, LLMUnavailableError


@pytest.fixture
def client():
    return LLMClient("http://localhost:8080", timeout_seconds=30.0, max_tokens=512)


async def test_complete_success(client):
    """正常なレスポンスでテキストを返すことを確認する."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"content": "要約結果です"}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await client.complete("テストプロンプト")

    assert result == "要約結果です"


async def test_complete_raises_on_connect_error(client):
    """接続エラー時に LLMUnavailableError を送出することを確認する."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.ConnectError("接続失敗"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(LLMUnavailableError):
            await client.complete("プロンプト")


async def test_complete_raises_on_timeout(client):
    """タイムアウト時に LLMUnavailableError を送出することを確認する."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.TimeoutException("タイムアウト"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(LLMUnavailableError):
            await client.complete("プロンプト")


async def test_complete_raises_on_empty_response(client):
    """空レスポンス時に LLMUnavailableError を送出することを確認する."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"content": ""}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(LLMUnavailableError):
            await client.complete("プロンプト")
