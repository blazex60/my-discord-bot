"""llama-cpp-python HTTP サーバーへの非同期クライアント."""

import httpx


class LLMUnavailableError(Exception):
    """LLM サーバーへの接続・応答に失敗したときに送出される."""


class LLMClient:
    """llama-cpp-python の /completion エンドポイントを呼び出すクライアント."""

    def __init__(self, base_url: str, timeout_seconds: float, max_tokens: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds
        self.max_tokens = max_tokens

    async def complete(self, prompt: str) -> str:
        """プロンプトを送信してテキストを生成する.

        Returns:
            生成されたテキスト文字列.

        Raises:
            LLMUnavailableError: 接続失敗・タイムアウト・空レスポンス時.
        """
        payload = {
            "prompt": prompt,
            "n_predict": self.max_tokens,
            "stop": [],
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/completion",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                text = data.get("content", "").strip()
                if not text:
                    raise LLMUnavailableError("LLM が空のレスポンスを返しました")
                return text
        except httpx.ConnectError as e:
            raise LLMUnavailableError(f"LLM サーバーに接続できません: {e}") from e
        except httpx.TimeoutException as e:
            raise LLMUnavailableError(f"LLM サーバーがタイムアウトしました: {e}") from e
        except httpx.HTTPStatusError as e:
            raise LLMUnavailableError(
                f"LLM サーバーがエラーを返しました: {e.response.status_code}"
            ) from e
