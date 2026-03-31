"""Discord VC 議事録自動作成ボット — メインエントリーポイント"""

import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

import discord
import yaml
from dotenv import load_dotenv

load_dotenv()  # .env ファイルから環境変数を読み込む

# 設定読み込み
with open("config.yaml") as f:
    config = yaml.safe_load(f)

# DISCORD_TOKEN は .env または環境変数から取得
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN が設定されていません。.env ファイルに記載するか環境変数を設定してください。"
    )

bot = discord.Bot()

# セッション管理
_active_sessions: dict[str, dict] = {}


@bot.event
async def on_ready():
    print(f"Bot 起動完了: {bot.user}")


@bot.slash_command(name="record_start", description="VC に参加して録音を開始する")
async def record_start(ctx: discord.ApplicationContext):
    if ctx.author.voice is None:
        await ctx.respond("VC チャンネルに参加してから実行してください。")
        return

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    voice_channel = ctx.author.voice.channel
    voice_client = await voice_channel.connect()

    _active_sessions[ctx.guild_id] = {
        "session_id": session_id,
        "voice_client": voice_client,
        "start_time": time.time(),
    }

    msg = await ctx.respond("🔴 録音中...")

    async def _on_timeout():
        max_hours = config["storage"]["max_recording_hours"]
        await msg.edit_original_response(
            content=f"⚠️ 最大録音時間 ({max_hours} 時間) に達したため自動停止しました。バッチ処理を開始します..."
        )
        if ctx.guild_id in _active_sessions:
            s = _active_sessions.pop(ctx.guild_id)
            await _run_batch_pipeline(msg, s["session_id"], s["start_time"])

    try:
        from pipeline.recorder import start_recording

        await start_recording(voice_client, session_id, on_timeout=_on_timeout())
    except Exception as e:
        await msg.edit_original_response(
            content=f"❌ エラーが発生しました: 録音開始失敗 ({e})\n"
            f"WAV ファイルは保持されています。`/transcribe_only` で再開できます。"
        )


@bot.slash_command(name="record_stop", description="録音を停止してバッチ処理を開始する")
async def record_stop(ctx: discord.ApplicationContext):
    session = _active_sessions.get(ctx.guild_id)
    if session is None:
        await ctx.respond("録音中のセッションがありません。")
        return

    session_id = session["session_id"]
    voice_client = session["voice_client"]
    start_time = session["start_time"]

    msg = await ctx.respond("⏳ バッチ処理を開始しました...")

    try:
        from pipeline.recorder import stop_recording

        wav_files = await stop_recording(session_id)
    except NotImplementedError:
        await msg.edit_original_response(
            content="❌ エラーが発生しました: recorder.py が未実装です"
        )
        return
    except Exception as e:
        await msg.edit_original_response(
            content=f"❌ エラーが発生しました: 録音停止失敗 ({e})\n"
            f"WAV ファイルは保持されています。`/transcribe_only` で再開できます。"
        )
        return
    finally:
        if voice_client.is_connected():
            await voice_client.disconnect()
        del _active_sessions[ctx.guild_id]

    await _run_batch_pipeline(msg, session_id, start_time)


@bot.slash_command(
    name="transcribe_only",
    description="既存の WAV ファイルから ASR・要約のみ再実行する（録音失敗時の再開用）",
)
async def transcribe_only(ctx: discord.ApplicationContext):
    # tmp/recordings/ から最新セッションの WAV を探す
    recordings_dir = Path(config["storage"]["tmp_dir"]) / "recordings"
    wav_files = sorted(recordings_dir.glob("*.wav"))
    if not wav_files:
        await ctx.respond("再処理する WAV ファイルが見つかりません。")
        return

    # 最新セッション ID を推定
    session_id = wav_files[-1].stem.split("_")[0] + "_" + wav_files[-1].stem.split("_")[1]

    msg = await ctx.respond("⏳ バッチ処理を開始しました...")
    await _run_batch_pipeline(msg, session_id, time.time())


async def _run_batch_pipeline(msg, session_id: str, start_time: float):
    """ASR → LLM の直列バッチ処理を実行し、進捗を Discord メッセージで更新する"""
    tmp_dir = Path(config["storage"]["tmp_dir"])
    output_dir = Path(config["storage"]["output_dir"])
    wav_files = sorted((tmp_dir / "recordings").glob(f"{session_id}*.wav"))
    total_wavs = max(len(wav_files), 1)

    # フェーズ2: ASR
    await msg.edit_original_response(
        content=f"🎤 音声認識処理中 (Whisper)... 0/{total_wavs} ファイル"
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
        content=f"🎤 音声認識処理中 (Whisper)... {total_wavs}/{total_wavs} ファイル"
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
            # 終了コード 2 = OOM による中断。生成済みチャンク要約を送信
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
            content=f"❌ エラーが発生しました: 出力ファイルが見つかりません"
        )
        return

    # tmp/ 以下の一時ファイルを削除
    for f in (tmp_dir / "recordings").glob(f"{session_id}*.wav"):
        f.unlink()
    for f in (tmp_dir / "transcripts").glob(f"{session_id}*"):
        f.unlink()


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
