"""Discord VC 議事録自動作成ボット — OBS録画 + チャットログ版"""

import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import discord
import yaml
from dotenv import load_dotenv

load_dotenv()

with open("config.yaml") as f:
    config = yaml.safe_load(f)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN が設定されていません。.env ファイルに記載するか環境変数を設定してください。"
    )

# メディアファイルの対応拡張子
SUPPORTED_EXTENSIONS = [".wav", ".mp4", ".mkv", ".webm", ".m4a", ".mp3", ".ogg", ".flac"]

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Bot(intents=intents)

# セッション管理: guild_id -> {session_id, start_time, start_dt, text_channel_id}
_active_sessions: dict[int, dict] = {}


@bot.event
async def on_ready():
    print(f"Bot 起動完了: {bot.user}")


@bot.slash_command(
    name="record_start", description="録音セッションを開始する（OBS で録音を開始してください）"
)
async def record_start(ctx: discord.ApplicationContext):
    if ctx.guild_id in _active_sessions:
        await ctx.respond("すでに録音セッションが進行中です。`/record_stop` で停止してください。")
        return

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    _active_sessions[ctx.guild_id] = {
        "session_id": session_id,
        "start_time": time.time(),
        "start_dt": datetime.now(timezone.utc),
        "text_channel_id": ctx.channel_id,
    }

    recordings_dir = Path(config["storage"]["tmp_dir"]) / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)

    ext_list = ", ".join(SUPPORTED_EXTENSIONS)
    await ctx.respond(
        f"🔴 録音セッション開始 (`{session_id}`)\n"
        f"OBS で録音を開始してください。\n"
        f"完了後、録音ファイル（{ext_list}）を `{recordings_dir}/` に保存してから `/record_stop` を実行してください。\n"
        f"このチャンネルのチャットログもセッション開始時刻以降のものを議事録に反映します。"
    )


@bot.slash_command(name="record_stop", description="録音を停止してバッチ処理を開始する")
async def record_stop(ctx: discord.ApplicationContext):
    session = _active_sessions.pop(ctx.guild_id, None)
    if session is None:
        await ctx.respond("録音中のセッションがありません。")
        return

    session_id = session["session_id"]
    start_time = session["start_time"]
    start_dt: datetime = session["start_dt"]
    text_channel_id: int = session["text_channel_id"]

    recordings_dir = Path(config["storage"]["tmp_dir"]) / "recordings"
    media_files = _find_media_files(recordings_dir)
    if not media_files:
        await ctx.respond(
            f"❌ `{recordings_dir}/` にメディアファイルが見つかりません。\n"
            f"OBS の出力先を確認してください。（対応形式: {', '.join(SUPPORTED_EXTENSIONS)}）"
        )
        return

    msg = await ctx.respond("⏳ チャットログを収集しています...")

    # チャットログ収集
    text_channel = bot.get_channel(text_channel_id)
    chat_path = await _collect_chat_log(text_channel, start_dt, session_id)
    chat_count = 0
    if chat_path:
        lines = chat_path.read_text(encoding="utf-8").splitlines()
        chat_count = len([ln for ln in lines if ln.strip()])

    await msg.edit_original_response(
        content=f"⏳ バッチ処理を開始しました... （チャットログ: {chat_count} 件）"
    )
    await _run_batch_pipeline(msg, session_id, start_time)


@bot.slash_command(
    name="transcribe_only",
    description="既存のファイルから ASR・要約のみ再実行する",
)
async def transcribe_only(ctx: discord.ApplicationContext):
    recordings_dir = Path(config["storage"]["tmp_dir"]) / "recordings"
    media_files = _find_media_files(recordings_dir)
    if not media_files:
        await ctx.respond("再処理するメディアファイルが見つかりません。")
        return

    # 最新ファイルのステム先頭2フィールドをセッション ID として使用
    stem = media_files[-1].stem
    parts = stem.split("_")
    session_id = f"{parts[0]}_{parts[1]}" if len(parts) >= 2 else stem

    msg = await ctx.respond("⏳ バッチ処理を開始しました...")
    await _run_batch_pipeline(msg, session_id, time.time())


def _find_media_files(recordings_dir: Path) -> list[Path]:
    """録音・録画ファイルを検索して返す。"""
    files = []
    for ext in SUPPORTED_EXTENSIONS:
        files.extend(recordings_dir.glob(f"*{ext}"))
    return sorted(files)


async def _collect_chat_log(channel, since: datetime, session_id: str) -> Path | None:
    """テキストチャンネルのチャットログを収集して保存する。

    Args:
        channel: Discord テキストチャンネル
        since: この時刻以降のメッセージを収集（UTC）
        session_id: セッション識別子

    Returns:
        チャットログファイルのパス（メッセージがなければ None）
    """
    if channel is None:
        return None

    transcripts_dir = Path(config["storage"]["tmp_dir"]) / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    messages = []
    try:
        async for msg in channel.history(after=since, oldest_first=True, limit=None):
            if msg.author.bot:
                continue
            if not msg.content.strip():
                continue
            ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            messages.append(f"[{ts}] {msg.author.display_name}: {msg.content}")
    except discord.Forbidden:
        return None

    if not messages:
        return None

    chat_path = transcripts_dir / f"{session_id}_chat.txt"
    chat_path.write_text("\n".join(messages), encoding="utf-8")
    return chat_path


async def _run_batch_pipeline(msg, session_id: str, start_time: float):
    """ASR → LLM の直列バッチ処理を実行し、進捗を Discord メッセージで更新する"""
    tmp_dir = Path(config["storage"]["tmp_dir"])
    output_dir = Path(config["storage"]["output_dir"])
    recordings_dir = tmp_dir / "recordings"
    media_files = _find_media_files(recordings_dir)
    total_files = max(len(media_files), 1)

    # フェーズ2: ASR
    await msg.edit_original_response(
        content=f"🎤 音声認識処理中 (Whisper)... 0/{total_files} ファイル"
    )
    result = subprocess.run(
        ["uv", "run", "python", "pipeline/transcriber.py", session_id],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        await msg.edit_original_response(
            content=f"❌ エラーが発生しました: ASR 処理失敗\n```{result.stderr[:500]}```"
        )
        return

    await msg.edit_original_response(
        content=f"🎤 音声認識処理中 (Whisper)... {total_files}/{total_files} ファイル"
    )

    # フェーズ3: LLM 要約
    await msg.edit_original_response(content="🧠 議事録生成中 (LLM)... チャンク 0/? を処理中")
    result = subprocess.run(
        ["uv", "run", "python", "pipeline/summarizer.py", session_id],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        partial = tmp_dir / f"partial_{session_id}.txt"
        if result.returncode == 2 and partial.exists():
            await msg.edit_original_response(
                content="❌ エラーが発生しました: VRAM 不足により LLM 処理を中断しました。"
                "生成済みのチャンク要約を送信します。"
            )
            await msg.channel.send(file=discord.File(str(partial)))
        else:
            await msg.edit_original_response(
                content=f"❌ エラーが発生しました: LLM 処理失敗\n```{result.stderr[:500]}```"
            )
        return

    # フェーズ4: 結果送信
    elapsed = round((time.time() - start_time) / 60, 1)
    output_path = output_dir / f"minutes_{session_id}.md"

    if output_path.exists():
        await msg.edit_original_response(
            content=f"✅ 議事録を生成しました（所要時間: {elapsed} 分）"
        )
        await msg.channel.send(file=discord.File(str(output_path)))
    else:
        await msg.edit_original_response(
            content="❌ エラーが発生しました: 出力ファイルが見つかりません"
        )
        return

    # tmp/ 以下の一時ファイルを削除
    for f in media_files:
        f.unlink()
    for f in (tmp_dir / "transcripts").glob(f"{session_id}*"):
        f.unlink()


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
