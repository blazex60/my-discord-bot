# vc-disconnect-bot

Discord Voice Channel 管理ボット。タイマー、アラーム、ユーザーキック・移動などの機能で VC の効率的な管理をサポート。

---

## 機能

- **複数 VC 同時タイマー対応** — ギルド内の複数の VC で独立したタイマーを同時管理
- **3 つのタイマーモード** — 相対時間（分）、絶対時間（時刻指定）、即時キック
- **自動キャンセル** — 全員が VC から退出すると自動的にタイマーをキャンセルしてボット退出
- **インメモリ状態管理** — 軽量・高速。永続化なし（再起動でリセット）
- **柔軟なユーザー操作** — キック・移動・一括移動に対応
- **警告通知** — 切断 60 秒前にメンバーに警告メッセージを送信

---

## コマンド一覧

### VC 参加・切断

| コマンド | 説明 |
|---|---|
| `/vc join` | ボットを現在の VC に参加させる（タイマーなし） |
| `/vc cancel` | 現在の VC のタイマーをキャンセルしてボット退出 |

### タイマー

| コマンド | 説明 | 例 |
|---|---|---|
| `/vc timer <minutes>` | N 分後に VC の全員を切断（1〜1440 分） | `/vc timer 30` |
| `/vc alarm <HH:MM>` | 指定時刻（JST）に VC の全員を切断 | `/vc alarm 22:00` |
| `/vc status` | 現在の VC のタイマー状態を表示（残り時間・モード） | `/vc status` |

### ユーザー操作

| コマンド | 説明 | 例 |
|---|---|---|
| `/vc kick <user> [user2] [user3]` | 指定ユーザーを即時切断（最大 3 人） | `/vc kick @alice @bob` |
| `/vc kick-timer <minutes> <user>` | N 分後に指定ユーザーを切断 | `/vc kick-timer 10 @alice` |
| `/vc move <user> <channel>` | 指定ユーザーを別の VC へ移動 | `/vc move @alice general-voice` |
| `/vc move-all <channel>` | 現在 VC の全員を別の VC へ移動（他Botは人間より優先して先に移動し、取り残しを防ぐ） | `/vc move-all other-voice` |

### ヘルプ

| コマンド | 説明 |
|---|---|
| `/help` | 利用可能なコマンド一覧を表示（自分にのみ表示）。詳しい使い方はリンク先のWebページを参照 |

---

## 必要な権限

ボットに以下の権限が必要です：

- `Connect` — VC に参加
- `Move Members` — ユーザーを別の VC へ移動

## 必要な Intent

[Discord Developer Portal](https://discord.com/developers/applications) のボット設定で **Server Members Intent** を有効にしてください。
これがオフだとコマンド実行者以外のメンバーがキャッシュされず、`/vc move-all` や `/vc kick` 等で実行者以外が認識されません。

---

## セットアップ

### 前提

- Python 3.12 以上
- uv
- Docker & Docker Compose（オプション）

### 環境設定

```bash
cp .env.example .env
```

`.env` に Discord Bot トークンを設定します：

```env
DISCORD_TOKEN=your_token_here
```

### 実行

#### uv を使用する場合

```bash
uv sync
uv run python bot.py
```

#### Docker を使用する場合

```bash
docker compose up --build
```

---

## 設定

`config.yaml` で以下を設定できます：

```yaml
bot:
  timezone: "Asia/Tokyo"           # タイムゾーン（JST 推奨）
  default_warning_seconds: 60      # 切断前の警告秒数
  help_url: ""                     # /help コマンドに表示する詳細ドキュメントのURL
```

---

## 開発

```bash
# テスト
uv run pytest

# フォーマット・リント
uv run ruff format .
uv run ruff check .
```

---

## 技術スタック

- **言語**: Python 3.12
- **ライブラリ**: py-cord >= 2.6
- **状態管理**: インメモリ dict（DB・LLM なし）
- **タイムゾーン**: zoneinfo（標準ライブラリ）
- **パッケージマネージャ**: uv
- **コンテナ**: Docker Compose

---

## 注意事項

- **永続化なし** — ボット再起動によってすべてのタイマーはリセットされます。
- **ボットが別の VC にいる場合** — 新しいタイマーコマンド実行時は参加しません。タイマーのみ動作し、Embed メッセージで通知します。
- **シークレット管理** — `DISCORD_TOKEN` は必ず `.env` に記載し、ソースコードにはコミットしないでください。
