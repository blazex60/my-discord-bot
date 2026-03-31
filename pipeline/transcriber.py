"""フェーズ2: Whisper ASR モジュール（subprocess として起動される）

使い方: python pipeline/transcriber.py <session_id>

処理フロー:
1. tmp/recordings/{session_id}_*.wav を収集
2. Whisper large-v3 (device="cuda") でロード
3. OOM 発生時は medium へフォールバックして再試行
4. セグメントのタイムスタンプ + ユーザー名でトランスクリプトを生成
5. tmp/transcripts/{session_id}_transcript.txt へ保存
6. del model → gc.collect() → cuda.empty_cache() でアンロード
"""

import gc
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

with open("config.yaml") as f:
    config = yaml.safe_load(f)

ASR_CONFIG = config["asr"]
STORAGE = config["storage"]


def _load_whisper(model_name: str):
    """Whisper モデルをロードする。OOM 時は呼び出し元でフォールバックする。"""
    import whisper

    logger.info("Whisper '%s' をロード中 (device=%s)...", model_name, ASR_CONFIG["device"])
    model = whisper.load_model(model_name, device=ASR_CONFIG["device"])
    logger.info("ロード完了: %s", model_name)
    return model


def _unload_whisper(model) -> None:
    """Whisper モデルをアンロードして VRAM を解放する。"""
    del model
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.info("VRAM を解放しました。")
    except ImportError:
        pass


def _transcribe_file(
    model, wav_path: Path, display_name: str, session_start: datetime
) -> list[str]:
    """WAV ファイルを文字起こしし、タイムスタンプ付きの行リストを返す。

    出力形式: [YYYY-MM-DD HH:MM:SS] ユーザー名: 発言内容

    Args:
        model: ロード済み Whisper モデル
        wav_path: 対象の WAV ファイル
        display_name: Discord の表示名
        session_start: セッション開始日時（session_id から算出）

    Returns:
        トランスクリプト行のリスト
    """
    logger.info("文字起こし中: %s (%s)", wav_path.name, display_name)
    result = model.transcribe(str(wav_path), language="ja", verbose=False)

    lines: list[str] = []
    for segment in result["segments"]:
        # セグメントの相対タイムスタンプを絶対日時へ変換
        abs_time = session_start + timedelta(seconds=segment["start"])
        timestamp = abs_time.strftime("%Y-%m-%d %H:%M:%S")
        text = segment["text"].strip()
        if text:
            lines.append(f"[{timestamp}] {display_name}: {text}")

    logger.info("  → %d セグメント", len(lines))
    return lines


def main(session_id: str) -> None:
    """セッション全体の WAV ファイルを文字起こしして transcript ファイルを生成する。"""
    tmp_dir = Path(STORAGE["tmp_dir"])
    recordings_dir = tmp_dir / "recordings"
    transcripts_dir = tmp_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    # WAV ファイルを収集
    wav_files = sorted(recordings_dir.glob(f"{session_id}_*.wav"))
    if not wav_files:
        logger.error("WAV ファイルが見つかりません: session_id=%s", session_id)
        sys.exit(1)

    logger.info("%d 個の WAV ファイルを処理します。", len(wav_files))

    # ユーザー名メタデータをロード（なければ user_id をそのまま使用）
    meta_path = transcripts_dir / f"{session_id}_meta.json"
    member_names: dict[str, str] = {}
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            member_names = json.load(f)

    # セッション開始日時を session_id から算出（YYYYMMDD_HHMMSS）
    try:
        session_start = datetime.strptime(session_id, "%Y%m%d_%H%M%S")
    except ValueError:
        session_start = datetime.now()
        logger.warning("session_id のパースに失敗しました。現在時刻を使用します。")

    # Whisper ロード（OOM 時は medium へフォールバック）
    primary = ASR_CONFIG["primary_model"].replace("whisper-", "")
    fallback = ASR_CONFIG["fallback_model"].replace("whisper-", "")

    model = None
    used_model = primary
    try:
        model = _load_whisper(primary)
    except Exception as e:
        import torch

        if isinstance(e, torch.cuda.OutOfMemoryError):
            logger.warning("OOM: large-v3 → %s へフォールバックします。", fallback)
            _unload_whisper(model) if model else None
            model = _load_whisper(fallback)
            used_model = fallback
        else:
            raise

    logger.info("使用モデル: whisper-%s", used_model)

    # 全 WAV ファイルを順次処理
    all_lines: list[tuple[str, str]] = []  # (timestamp_str, line)

    for i, wav_path in enumerate(wav_files, 1):
        # ファイル名から user_id を抽出: {session_id}_{user_id}.wav
        user_id = wav_path.stem.removeprefix(f"{session_id}_")
        display_name = member_names.get(user_id, user_id)

        logger.info("[%d/%d] %s", i, len(wav_files), wav_path.name)
        lines = _transcribe_file(model, wav_path, display_name, session_start)
        for line in lines:
            # タイムスタンプ部分を抽出してソート用キーとして保持
            ts = line[1:20]  # "[YYYY-MM-DD HH:MM:SS]" → "YYYY-MM-DD HH:MM:SS"
            all_lines.append((ts, line))

    # タイムスタンプでソートして統合
    all_lines.sort(key=lambda x: x[0])
    transcript_lines = [line for _, line in all_lines]

    # モデルアンロード
    _unload_whisper(model)

    # トランスクリプト保存
    output_path = transcripts_dir / f"{session_id}_transcript.txt"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(transcript_lines))
        f.write("\n")

    logger.info("トランスクリプト保存: %s (%d 行)", output_path, len(transcript_lines))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: python pipeline/transcriber.py <session_id>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])
