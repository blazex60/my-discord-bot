"""フェーズ1: Discord VC 録音モジュール

py-cord の WaveSink を使い、ユーザーIDごとに WAV ファイルへ録音する。
ファイル命名: tmp/recordings/{YYYYMMDD_HHMMSS}_{user_id}.wav
メタデータ: tmp/transcripts/{session_id}_meta.json  (user_id → display_name のマッピング)
"""

import asyncio
import json
import logging
import warnings
from pathlib import Path

import yaml
from discord.sinks import WaveSink

logger = logging.getLogger(__name__)

with open("config.yaml") as f:
    config = yaml.safe_load(f)

# session_id → {"voice_client": ..., "wav_done": Future, "timeout_task": Task | None}
_sessions: dict[str, dict] = {}


async def start_recording(
    voice_client,
    session_id: str,
    on_timeout: "callable | None" = None,
) -> None:
    """録音を開始する。

    Args:
        voice_client: py-cord の VoiceClient
        session_id: セッション識別子（YYYYMMDD_HHMMSS 形式）
        on_timeout: 最大録音時間超過時に呼び出す非同期関数（省略可）
    """
    recordings_dir = Path(config["storage"]["tmp_dir"]) / "recordings"
    transcripts_dir = Path(config["storage"]["tmp_dir"]) / "transcripts"
    recordings_dir.mkdir(parents=True, exist_ok=True)
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    # VC チャンネルメンバーの user_id → display_name マッピングを保存
    member_names: dict[str, str] = {}
    if voice_client.channel:
        for member in voice_client.channel.members:
            member_names[str(member.id)] = member.display_name

    meta_path = transcripts_dir / f"{session_id}_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(member_names, f, ensure_ascii=False)
    logger.info("メタデータ保存: %s", meta_path)

    loop = asyncio.get_event_loop()
    wav_done: asyncio.Future[list[str]] = loop.create_future()

    async def _finished_callback(sink: WaveSink, channel) -> None:
        """録音終了時に各ユーザーの音声を WAV ファイルへ保存する"""
        paths: list[str] = []
        for user_id, audio in sink.audio_data.items():
            filename = f"{session_id}_{user_id}.wav"
            filepath = recordings_dir / filename
            with open(filepath, "wb") as f:
                f.write(audio.file.getvalue())
            logger.info("WAV 保存: %s", filepath)
            paths.append(str(filepath))

        if not wav_done.done():
            wav_done.set_result(paths)

    # VoiceClient の WebSocket 接続が安定するまで短時間待機
    await asyncio.sleep(0.5)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        voice_client.start_recording(WaveSink(), _finished_callback, voice_client.channel)
    logger.info("録音開始: session_id=%s", session_id)

    # 最大録音時間タイマー
    timeout_task: asyncio.Task | None = None
    max_hours: float = config["storage"]["max_recording_hours"]

    if max_hours > 0:

        async def _timeout_handler() -> None:
            await asyncio.sleep(max_hours * 3600)
            logger.warning("最大録音時間 (%s 時間) に達しました。自動停止します。", max_hours)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                voice_client.stop_recording()
            if on_timeout is not None:
                await on_timeout()

        timeout_task = asyncio.create_task(_timeout_handler())

    _sessions[session_id] = {
        "voice_client": voice_client,
        "wav_done": wav_done,
        "timeout_task": timeout_task,
    }


async def stop_recording(session_id: str) -> list[str]:
    """録音を停止し、生成された WAV ファイルのパスリストを返す。

    Returns:
        保存された WAV ファイルの絶対パスリスト（ユーザーごとに 1 ファイル）

    Raises:
        KeyError: session_id が存在しない場合
    """
    session = _sessions.pop(session_id)
    voice_client = session["voice_client"]
    wav_done: asyncio.Future[list[str]] = session["wav_done"]
    timeout_task: asyncio.Task | None = session["timeout_task"]

    # タイマーキャンセル
    if timeout_task is not None and not timeout_task.done():
        timeout_task.cancel()

    # 録音停止 → _finished_callback が wav_done を set_result する
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        voice_client.stop_recording()
    logger.info("録音停止: session_id=%s", session_id)

    return await wav_done
