<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-23 | Updated: 2026-04-23 -->

# tests

## Purpose

discord-minutes-bot の pytest テストスイート。現時点は軽量なユニットテストのみ。
LLM・Whisper モデルを実際にロードするテストは含まない（VRAM 消費・実行時間の問題）。

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | パッケージ初期化（空） |
| `conftest.py` | 共通フィクスチャ（`config` fixture: config.yaml 読み込み、`tmp_recordings_dir`: 一時録音ディレクトリ） |
| `test_chunker.py` | `utils/chunker.py` のユニットテスト（現在はプレースホルダー） |
| `test_bot_config.py` | `config.yaml` の構造・必須キー検証テスト |
| `test_memory.py` | `utils/memory.py` の動作テスト |

## For AI Agents

### Working In This Directory

- テスト実行: `uv run pytest tests/`（discord-minutes-bot/ ディレクトリから）
- LLM・Whisper モデルを実ロードするテストは追加しない
- `llm.tokenize()` 等は `unittest.mock.MagicMock` で代替する
- `conftest.py` のフィクスチャを積極的に再利用する

### Testing Requirements

- `test_chunker.py` にはプレースホルダーが残っている → `chunker.py` 実装後に実テストを追加する
- DB・ファイル I/O テストは `tmp_path` または `tmp_recordings_dir` フィクスチャを使用する

### Common Patterns

```python
# LLM モックのパターン
from unittest.mock import MagicMock
mock_llm = MagicMock()
mock_llm.tokenize.return_value = [0] * 10  # 10 トークンとして返す
```

## Dependencies

### Internal

- `config.yaml`（conftest.py が読み込む）
- `utils/chunker.py`, `utils/memory.py`（各テストがインポート）

### External

| パッケージ | 用途 |
|---|---|
| `pytest` | テストランナー |
| `PyYAML` | conftest.py での config 読み込み |

<!-- MANUAL: -->
