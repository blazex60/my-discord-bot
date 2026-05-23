# CLAUDE.md — vc-disconnect-bot

## 概要

指定時刻またはカウントダウンタイマーで Discord VC の全メンバーを強制切断する Bot。
LLM・データベース・外部サービス一切なし。

---

## 開発環境

| 項目 | 内容 |
|---|---|
| Python | 3.12 |
| パッケージ管理 | `uv` |
| Discord ライブラリ | py-cord >= 2.6 |
| デプロイ | Docker Compose |

---

## よく使うコマンド

```bash
# 依存関係インストール
uv sync

# Bot 起動（.env に DISCORD_TOKEN が必要）
uv run python bot.py

# テスト
uv run pytest

# フォーマット / リント
uv run ruff format .
uv run ruff check .

# Docker で起動
docker compose up --build
```

---

## 設計上の制約

- **タイマーは永続化しない** — Bot 再起動でタイマーはリセットされる（仕様）
- **DB 不要** — `_guild_states` dict のみで状態管理
- **LLM 不使用** — 外部 AI API は一切使わない
- **ZoneInfo を使う** — `pytz` や `dateutil` は使わない（stdlib の `zoneinfo` を使う）
- **`move_members` 権限が必須** — `member.move_to(None)` に必要

## シークレット管理

- `DISCORD_TOKEN` は必ず `.env` に書く
- `config.yaml` にシークレットを書かない
