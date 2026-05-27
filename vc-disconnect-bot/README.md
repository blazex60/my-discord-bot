# vc-disconnect-bot

指定時刻またはカウントダウンタイマーで Discord VC の全メンバー（または特定メンバー）を強制切断・移動する Bot。

---

## 機能

- 複数 VC に同時タイマーを設定可能（ギルド内の各 VC が独立して動作）
- 全員切断 / 特定ユーザー切断（即時・タイマー）
- VC 間メンバー移動（特定ユーザー・全員）
- 全人間メンバーが退出した VC のタイマーを自動キャンセル
- タイマー発火 60 秒前に警告メッセージを送信

---

## コマンド一覧

| コマンド | 説明 |
|---|---|
| `/vc join` | ボットを現在の VC に参加させる（タイマーなし） |
| `/vc timer <minutes>` | N 分後に VC の全員を切断（1〜1440 分） |
| `/vc alarm <HH:MM>` | 指定時刻（JST）に VC の全員を切断 |
| `/vc status` | 現在の VC のタイマー状態を表示 |
| `/vc cancel` | 現在の VC のタイマーをキャンセルしてボット退出 |
| `/vc kick <user> [user2] [user3]` | 指定ユーザーを即時切断（最大 3 人） |
| `/vc kick-timer <minutes> <user>` | N 分後に指定ユーザーを切断 |
| `/vc move <user> <channel>` | 指定ユーザーを別の VC へ移動 |
| `/vc move-all <channel>` | 現在 VC の全員を別の VC へ移動 |

---

## セットアップ

### 必要な権限

Bot に以下の権限を付与してください。

- `Connect`
- `Move Members`

### 1. トークン設定

```bash
cp .env.example .env  # または直接作成
```

`.env` に Discord Bot トークンを記載します。

```env
DISCORD_TOKEN=your_token_here
```

### 2. 依存関係インストール

```bash
uv sync
```

### 3. Bot 起動

```bash
uv run python bot.py
```

---

## Docker で起動

```bash
docker compose up --build
```

コンテナは `restart: unless-stopped` で自動再起動します。

---

## 設定

`config.yaml` で動作を調整できます。

```yaml
bot:
  timezone: "Asia/Tokyo"        # 表示用タイムゾーン（変更不要）
  default_warning_seconds: 60   # 切断前の警告を送るタイミング（秒）
```

---

## 開発

```bash
# テスト
uv run pytest

# フォーマット / リント
uv run ruff format .
uv run ruff check .
```

---

## 注意事項

- タイマーは **永続化しない** — Bot 再起動でリセットされます（仕様）
- 同一ギルドで Bot が入居できる VC は 1 つのみ（py-cord の制約）。複数 VC にタイマーを設定した場合、2 つ目以降の VC にはボットが入居しませんがタイマーは正常に動作します
- `DISCORD_TOKEN` は必ず `.env` に記載し、ソースコードにはコミットしないでください
