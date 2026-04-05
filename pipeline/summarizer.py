"""フェーズ3: llama.cpp LLM 要約モジュール（subprocess として起動される）

使い方: python pipeline/summarizer.py <session_id>

処理フロー:
1. tmp/transcripts/{session_id}_transcript.txt を読み込む
2. tmp/transcripts/{session_id}_chat.txt を読み込む（存在する場合）
3. Llama クラスで GGUF モデルをロード
4. Step 1: 各チャンクの要点を生成
5. Step 2: 全チャンク要約 + チャットログを統合して Markdown を生成
6. output/minutes_{session_id}.md へ保存
7. del llm → gc.collect() → cuda.empty_cache() でアンロード

エラー時:
- OOM: 生成済みチャンク要約を tmp/partial_{session_id}.txt に保存して終了
"""

import gc
import logging
import sys
from pathlib import Path

# 親ディレクトリをPythonパスに追加（utils モジュールをインポートするため）
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

with open("config.yaml") as f:
    config = yaml.safe_load(f)

LLM_CONFIG = config["llm"]
STORAGE = config["storage"]

# プロンプトテンプレート
_CHUNK_SUMMARY_PROMPT = """\
以下は会議の一部の音声文字起こしです。この部分の要点を箇条書きで日本語にまとめてください。
決定事項やToDo（誰が何をするか）があれば特に明記してください。

--- 音声文字起こし ---
{transcript}
--- ここまで ---

要点:"""

_FINAL_SUMMARY_PROMPT_WITH_CHAT = """\
以下は会議の音声文字起こしの要点まとめと、会議中のチャットログです。
これらを統合して、以下の構成でMarkdown形式の議事録を日本語で作成してください。

## 会議の概要
（会議で話し合われた主なテーマと結果を2〜4文で記述）

## 決定事項
（会議で決まったことを箇条書きで記述。なければ「特になし」）

## ToDo
（誰が何をするかを箇条書きで記述。なければ「特になし」）

## チャットメモ
（チャットログの中で議事録に残すべき重要な内容を箇条書きで記述。なければ「特になし」）

--- 音声文字起こしの要点 ---
{chunk_summaries}
--- ここまで ---

--- チャットログ ---
{chat_log}
--- ここまで ---

議事録:"""

_FINAL_SUMMARY_PROMPT_NO_CHAT = """\
以下は会議全体の各パートの要点まとめです。
これらを統合して、以下の構成でMarkdown形式の議事録を日本語で作成してください。

## 会議の概要
（会議で話し合われた主なテーマと結果を2〜4文で記述）

## 決定事項
（会議で決まったことを箇条書きで記述。なければ「特になし」）

## ToDo
（誰が何をするかを箇条書きで記述。なければ「特になし」）

--- 各パートの要点 ---
{chunk_summaries}
--- ここまで ---

議事録:"""


def _load_llm():
    """llama-cpp-python の Llama モデルをロードする。"""
    from llama_cpp import Llama

    model_path = LLM_CONFIG["model_path"]
    if not Path(model_path).exists():
        raise FileNotFoundError(
            f"モデルファイルが見つかりません: {model_path}\n"
            f"models/ ディレクトリに GGUF ファイルを配置してください。"
        )

    logger.info("LLM ロード中: %s", model_path)

    llm = Llama.from_pretrained(
	    repo_id="unsloth/gemma-4-26B-A4B-it-GGUF",
	    filename="gemma-4-26B-A4B-it-UD-Q6_K.gguf",
    )
    logger.info("LLM ロード完了")
    return llm


def _unload_llm(llm) -> None:
    """LLM をアンロードして VRAM と RAM を解放する。"""
    del llm
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.info("VRAM を解放しました。")
    except ImportError:
        pass


def _generate(llm, prompt: str) -> str:
    """LLM で推論を実行してテキストを生成する。タイムアウトは設定しない（夜間バッチ前提）。"""
    output = llm(
        prompt,
        max_tokens=1024,
        temperature=0.2,
        top_p=0.95,
        repeat_penalty=1.1,
        echo=False,
    )
    return output["choices"][0]["text"].strip()


def _summarize_chunk(llm, chunk: str, index: int, total: int) -> str:
    """チャンク1つを要約する（Step 1）。"""
    logger.info("チャンク要約 [%d/%d]...", index, total)
    prompt = _CHUNK_SUMMARY_PROMPT.format(transcript=chunk)
    return _generate(llm, prompt)


def _generate_final_minutes(llm, chunk_summaries: list[str], chat_log: str | None) -> str:
    """全チャンク要約（+ チャットログ）を統合して最終議事録 Markdown を生成する（Step 2）。"""
    logger.info("統合要約を生成中...")
    combined = "\n\n".join(f"【パート {i + 1}】\n{s}" for i, s in enumerate(chunk_summaries))

    if chat_log:
        prompt = _FINAL_SUMMARY_PROMPT_WITH_CHAT.format(
            chunk_summaries=combined,
            chat_log=chat_log,
        )
    else:
        prompt = _FINAL_SUMMARY_PROMPT_NO_CHAT.format(chunk_summaries=combined)

    return _generate(llm, prompt)


def main(session_id: str) -> None:
    """セッションのトランスクリプトとチャットログを2段階要約して議事録 Markdown を生成する。"""
    tmp_dir = Path(STORAGE["tmp_dir"])
    output_dir = Path(STORAGE["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    transcript_path = tmp_dir / "transcripts" / f"{session_id}_transcript.txt"
    if not transcript_path.exists():
        logger.error("トランスクリプトが見つかりません: %s", transcript_path)
        sys.exit(1)

    transcript = transcript_path.read_text(encoding="utf-8")
    if not transcript.strip():
        logger.error("トランスクリプトが空です。")
        sys.exit(1)

    logger.info("トランスクリプト読み込み完了: %d 文字", len(transcript))

    # チャットログ読み込み（存在する場合のみ）
    chat_log: str | None = None
    chat_path = tmp_dir / "transcripts" / f"{session_id}_chat.txt"
    if chat_path.exists():
        chat_log = chat_path.read_text(encoding="utf-8").strip() or None
        if chat_log:
            logger.info("チャットログ読み込み完了: %d 文字", len(chat_log))
    else:
        logger.info("チャットログなし（音声のみで議事録を生成します）")

    # LLM ロード
    try:
        llm = _load_llm()
    except FileNotFoundError as e:
        logger.error("%s", e)
        sys.exit(1)

    # チャンク分割
    from utils.chunker import split_into_chunks

    max_tokens = LLM_CONFIG.get("chunk_size_tokens", 2200)
    chunks = split_into_chunks(transcript, llm, max_tokens=max_tokens)
    logger.info("チャンク数: %d", len(chunks))

    # Step 1: チャンクごとの要約
    chunk_summaries: list[str] = []
    partial_path = tmp_dir / f"partial_{session_id}.txt"

    try:
        for i, chunk in enumerate(chunks, 1):
            summary = _summarize_chunk(llm, chunk, i, len(chunks))
            chunk_summaries.append(summary)
            # OOM リスクに備えて都度保存
            partial_path.write_text("\n\n---\n\n".join(chunk_summaries), encoding="utf-8")
    except Exception as e:
        import torch

        if isinstance(e, torch.cuda.OutOfMemoryError):
            logger.error("OOM: LLM 処理を中断します。生成済み要約を保存しました: %s", partial_path)
            _unload_llm(llm)
            sys.exit(2)  # 終了コード 2 = OOM による中断
        raise

    # Step 2: 統合要約 → 最終議事録 Markdown
    try:
        minutes_md = _generate_final_minutes(llm, chunk_summaries, chat_log)
    except Exception as e:
        import torch

        if isinstance(e, torch.cuda.OutOfMemoryError):
            logger.error("OOM: 統合要約を中断します。チャンク要約を保存しました: %s", partial_path)
            _unload_llm(llm)
            sys.exit(2)
        raise

    # LLM アンロード
    _unload_llm(llm)

    # 議事録を output/ へ保存
    output_path = output_dir / f"minutes_{session_id}.md"
    output_path.write_text(minutes_md, encoding="utf-8")
    logger.info("議事録保存: %s", output_path)

    # partial ファイルは不要なので削除
    if partial_path.exists():
        partial_path.unlink()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: python pipeline/summarizer.py <session_id>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])
