<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-23 | Updated: 2026-04-23 -->

# pipeline

## Purpose

ASR（文字起こし）と LLM 要約の2つのサブプロセスモジュールを格納する。
`bot.js` から `uv run python pipeline/transcriber.py <session_id>` / `uv run python pipeline/summarizer.py <session_id>` として起動される。
各スクリプトはフェーズ終了時にモデルをアンロードして VRAM を解放する。

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | パッケージ初期化（空） |
| `transcriber.py` | フェーズ2: Whisper ASR。WAV → タイムスタンプ付きトランスクリプト（`{sessionId}_transcript.txt`） |
| `summarizer.py` | フェーズ3: llama-cpp-python 2段階要約。トランスクリプト + チャットログ → 議事録 Markdown |

## For AI Agents

### Working In This Directory

- 両スクリプトは `sys.path.insert(0, parent)` で `utils/` モジュールをインポートする。パスを変更しない
- `config.yaml` は **プロジェクトルート（discord-minutes-bot/）から** 読む（スクリプトの CWD = プロジェクトルートを前提とする）
- モデルアンロードは必ずフェーズ終了時に実施: `del model → gc.collect() → torch.cuda.empty_cache()`
- タイムアウトは設定しない（夜間バッチ処理前提）

### transcriber.py の仕様

- 入力: `tmp/recordings/{session_id}*.wav`
- OOM フォールバック順: `large-v3 (CUDA)` → `medium (CUDA)` → `medium (CPU)`
- メタデータ: `tmp/transcripts/{session_id}_meta.json`（userId → displayName マッピング）
- 出力: `tmp/transcripts/{session_id}_transcript.txt`（`[YYYY-MM-DD HH:MM:SS] ユーザー名: 発言内容` 形式、タイムスタンプ昇順）
- 失敗時: `sys.exit(1)`

### summarizer.py の仕様

- 入力: `tmp/transcripts/{session_id}_transcript.txt`（必須）、`{session_id}_chat.txt`（任意）
- LLM: Gemma-4-26B GGUF（`Llama.from_pretrained` で HuggingFace からロード）
- チャンク分割: `utils/chunker.split_into_chunks()` を使用（max_tokens = config の `chunk_size_tokens`）
- 2段階要約: Step1 = チャンクごとの要点生成、Step2 = 全要点 + チャットログ統合 → Markdown
- OOM 時: 生成済みチャンク要約を `tmp/partial_{session_id}.txt` に保存して `sys.exit(2)`（終了コード 2 = OOM）
- 出力: `output/minutes_{session_id}.md`

### Testing Requirements

- モデルを実際にロードするテストは書かない
- LLM・Whisper は必ずモックで代替する
- ファイル I/O は `tmp_path` フィクスチャを使用する

### Common Patterns

```python
# OOM フォールバックパターン（transcriber.py）
try:
    model = _load_whisper(primary, device=device)
except torch.cuda.OutOfMemoryError:
    gc.collect(); torch.cuda.empty_cache()
    model = _load_whisper(fallback, device=device)
```

```python
# OOM 中断パターン（summarizer.py, exit code 2）
except torch.cuda.OutOfMemoryError:
    _unload_llm(llm)
    sys.exit(2)
```

## Dependencies

### Internal

- `utils/chunker.py` — `summarizer.py` がチャンク分割に使用
- `utils/memory.py` — `unload_model()` の参照実装（pipeline 内では同等処理を直接実装）

### External

| パッケージ | 用途 |
|---|---|
| `openai-whisper` | ASR モデル（large-v3 / medium） |
| `llama-cpp-python` | LLM 推論エンジン（Llama クラス） |
| `torch` | CUDA OOM 検出・VRAM 解放 |
| `PyYAML` | config.yaml 読み込み |

<!-- MANUAL: -->
