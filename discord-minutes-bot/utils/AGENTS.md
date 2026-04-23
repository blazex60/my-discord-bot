<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-04-23 | Updated: 2026-04-23 -->

# utils

## Purpose

discord-minutes-bot 全体で使用する共通ユーティリティを格納する。
チャンク分割（`chunker.py`）とモデルアンロード（`memory.py`）の2つのモジュールのみを含む。

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | パッケージ初期化（空） |
| `chunker.py` | llm.tokenize() を使ったトークン数ベースのテキストチャンク分割 |
| `memory.py` | モデルを安全にアンロードして VRAM と RAM を解放するユーティリティ |

## For AI Agents

### Working In This Directory

- `chunker.py` は `llama-cpp-python` の `Llama` インスタンスを引数で受け取る。モデルをここでロードしない
- `memory.py` の `unload_model()` は pipeline 内でも同等処理を直接実装しているが、共通インターフェースとして維持する
- 新しいユーティリティを追加するときは、特定の pipeline スクリプトにしか使わないロジックはここに置かない

### chunker.py の仕様

```python
split_into_chunks(text: str, llm: Llama, max_tokens: int = 2200) -> list[str]
```

- 行単位で分割 → トークン数を計算 → 上限を超えない範囲でチャンクを構築
- 1行がトークン上限を超える場合は句読点（。、！？.!?）で文分割、さらに超える場合は文字数等分
- `max_tokens` のデフォルトは 2200（`config.yaml` の `llm.chunk_size_tokens` から `summarizer.py` が渡す）

### memory.py の仕様

```python
unload_model(model) -> None
```

- `del model → gc.collect() → torch.cuda.empty_cache()`
- `torch` 未インストール環境でも `ImportError` を握りつぶして安全に動作する

### Testing Requirements

- `chunker.py` のテストは LLM モックを使用（`llm.tokenize()` をモック）
- `memory.py` は `torch` なし環境でも動作することをテストする

### Common Patterns

```python
# chunker の使用例（summarizer.py 内）
from utils.chunker import split_into_chunks
chunks = split_into_chunks(transcript, llm, max_tokens=2200)
```

```python
# memory の使用例
from utils.memory import unload_model
unload_model(model)
```

## Dependencies

### Internal

なし（他の utils モジュールに依存しない）

### External

| パッケージ | 用途 |
|---|---|
| `llama-cpp-python` | `chunker.py` が `llm.tokenize()` を使用 |
| `torch` | `memory.py` が VRAM 解放に使用（オプション依存） |

<!-- MANUAL: -->
