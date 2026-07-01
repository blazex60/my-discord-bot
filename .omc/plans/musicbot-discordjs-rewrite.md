# Plan: music-bot を py-cord → discord.js へ完全書き直し

**Status:** pending approval  
**Created:** 2026-06-26  
**Scope:** music-bot/ ディレクトリ全体の Python→Node.js 移植

---

## 背景・動機

py-cord の VoiceClient は VC 周りで複数の根本的な問題を抱えている：

- `connect()` に `self_deaf` パラメータがない（`Connectable.connect()` が渡さない）
- `change_voice_state(self_deaf=True)` を後から呼ぶと VOICE_STATE_UPDATE が再発行され voice WS が close code 1000 で切断される
- DAVE E2EE のサポートが不完全（`davey` パッケージ依存、モジュールパッチが必要）
- py-cord 2.7 で `discord.VoiceClient` が deprecated、`discord.voice.VoiceClient` への移行が必要

discord.js v14 + @discordjs/voice はこれらを根本的に解決する：
- `joinVoiceChannel({ selfDeaf: true })` がネイティブ対応
- DAVE 対応済み（4017 エラーなし）
- AudioPlayer の状態機械が明示的で信頼性が高い

---

## Requirements Summary

- 全スラッシュコマンドの機能等価性維持（/play, /pause, /resume, /skip, /stop, /leave, /queue, /shuffle, /loop, /volume, /nowplaying, /bitrate）
- yt-dlp と FFmpeg はシステムバイナリを引き続き使用
- Docker Compose 環境維持（.env, restart: unless-stopped）
- DISCORD_TOKEN は .env のみ（ソースコード不可）

---

## Technology Stack

| 用途 | Python (現在) | Node.js (新規) |
|---|---|---|
| Discord ライブラリ | py-cord >= 2.6 | discord.js v14 |
| Voice | py-cord[voice] | @discordjs/voice |
| Opus エンコーダ | 内蔵 | @discordjs/opus (prebuilt) または opusscript |
| 暗号化 | 内蔵 | libsodium-wrappers |
| YouTube | yt-dlp (Python wrap) | yt-dlp (システム CLI, child_process) |
| 音声処理 | FFmpeg (システム) | FFmpeg (システム、同じ) |
| ランタイム | Python 3.12 | Node.js 20 LTS (Alpine) |
| パッケージ管理 | uv | npm |

---

## File Mapping

| Python (現在) | Node.js (新規) | 主な変換内容 |
|---|---|---|
| bot.py | src/index.js | Client, interactionCreate, voiceStateUpdate, セッション管理 |
| bot.py (commands) | src/commands/*.js | 各コマンドを個別ファイルで実装 |
| player.py | src/player.js | GuildPlayer, Watchdog, AudioPlayer ラッパー |
| queue_manager.py | src/queue.js | GuildQueue, LoopMode, Track |
| search.py | src/search.js | yt-dlp CLI ラッパー |
| views.py | src/views.js | ButtonBuilder 検索結果 UI |
| - | src/deploy.js | スラッシュコマンド登録スクリプト |

---

## Implementation Steps

### Step 1: プロジェクト初期化

**package.json 作成:**
```json
{
  "name": "music-bot",
  "version": "1.0.0",
  "type": "module",
  "main": "src/index.js",
  "engines": { "node": ">=20" },
  "dependencies": {
    "discord.js": "^14",
    "@discordjs/voice": "^0.17",
    "@discordjs/opus": "^0.10",
    "libsodium-wrappers": "^0.7",
    "dotenv": "^16"
  }
}
```

**.env 追加項目:** `CLIENT_ID` (スラッシュコマンド登録に必要)

### Step 2: src/queue.js — GuildQueue

```js
// Track { title, webpageUrl, streamUrl, duration, requestedBy, thumbnail }
// LoopMode: 'off' | 'track' | 'queue'
// GuildQueue: add(track), next(forceAdvance), clear(), shuffle(), cycleLoop(), current, upcoming()
```

queue_manager.py の 1:1 変換。Python の dataclass → 普通のオブジェクト。

### Step 3: src/search.js — yt-dlp ラッパー

```js
// searchYoutube(query) → spawn yt-dlp ['--dump-json', 'ytsearch5:query']
// resolveMetadata(url)  → spawn yt-dlp ['--dump-json', url]
// resolveStreamUrl(url) → spawn yt-dlp ['-f', 'bestaudio', '--get-url', url]
```

Python の `asyncio.to_thread` → Node.js の `new Promise` + `spawn` (ノンブロッキング)。

### Step 4: src/player.js — GuildPlayer

```js
// @discordjs/voice の AudioPlayer ラッパー
// - play(track): resolveStreamUrl → createAudioResource → audioPlayer.play()
// - AudioPlayerStatus.Idle → handleAfter() → queue.next() → play() 再帰
// - Watchdog: setInterval で 10s 毎に audioPlayer.state 確認、30s 無音で force skip
// - pause() / resume() / skip() / stop() / setVolume()
```

**重要:** `asyncio.run_coroutine_threadsafe` の代替は不要。Node.js はシングルスレッドで
`AudioPlayerStatus.Idle` イベントはメインスレッドで発火する。

### Step 5: src/index.js — メイン

```js
// Client({ intents: [GuildVoiceStates, Guilds] })
// ready イベント: スラッシュコマンド登録 (CLIENT_ID が設定されている場合)
// interactionCreate: isChatInputCommand() → コマンドディスパッチ
// interactionCreate: isButton() → SearchResultView のボタン処理
// voiceStateUpdate: 全員退出時の自動退出
// VoiceConnection:
//   joinVoiceChannel({ selfDeaf: true })  ← self_deaf 問題が根本解決
```

### Step 6: src/commands/ — スラッシュコマンド群

各ファイル: `{ data: SlashCommandBuilder, execute(interaction, sessions) }`

| ファイル | コマンド | 主な変換ポイント |
|---|---|---|
| play.js | /play | URL 判定, SearchResultView 表示 |
| pause.js | /pause | audioPlayer.pause() |
| resume.js | /resume | audioPlayer.unpause() |
| skip.js | /skip | forceSkip フラグ + audioPlayer.stop() |
| stop.js | /stop | queue.clear() + audioPlayer.stop() |
| leave.js | /leave | connection.destroy() |
| queue.js | /queue | sessions から queue 取得, embed 生成 |
| shuffle.js | /shuffle | queue.shuffle() |
| loop.js | /loop | queue.cycleLoop() |
| volume.js | /volume | audioPlayer resource.volume.setVolume() |
| nowplaying.js | /nowplaying | EmbedBuilder |
| bitrate.js | /bitrate | channel.setBitrate() |

### Step 7: src/views.js — 検索結果ボタン UI

```js
// 検索結果5件を ActionRow (3個) + ActionRow (2個) のボタンで表示
// ButtonBuilder x5, customId に index を埋め込み
// interactionCreate isButton() → index → on_select コールバック
```

`discord.ui.View` (py-cord) → `ActionRowBuilder + ButtonBuilder` (discord.js)。  
コールバックは `SessionManager.pendingSelections` Map で管理。

### Step 8: Dockerfile 更新

```dockerfile
FROM node:20-alpine
RUN apk add --no-cache ffmpeg python3 py3-pip && \
    pip3 install --break-system-packages yt-dlp
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY src/ ./src/
CMD ["node", "src/index.js"]
```

### Step 9: src/deploy.js — コマンド登録スクリプト

```js
// REST().setToken(DISCORD_TOKEN).put(Routes.applicationCommands(CLIENT_ID), { body: commands })
// 初回セットアップ時に手動実行: node src/deploy.js
// または start 時に CLIENT_ID 環境変数があれば自動登録
```

---

## Key Design Decisions

### self_deaf の解決
discord.js + @discordjs/voice:
```js
joinVoiceChannel({
  channelId: channel.id,
  guildId: guild.id,
  adapterCreator: guild.voiceAdapterCreator,
  selfDeaf: true,  // ← ネイティブ対応。WS close 1000 問題なし
})
```

### yt-dlp との統合
Python の `asyncio.to_thread` → Node.js の spawn Promise パターン:
```js
function spawnAsync(cmd, args) {
  return new Promise((resolve, reject) => {
    const proc = spawn(cmd, args)
    let stdout = ''
    proc.stdout.on('data', d => stdout += d)
    proc.on('close', code => code === 0 ? resolve(stdout) : reject(new Error(`exit ${code}`)))
  })
}
```

### Watchdog の実装
py-cord の `_WatchdogSource`（読み取りフック）→ discord.js の `AudioPlayer` イベント:
- `AudioPlayerStatus.Playing` → lastReadAt 更新
- `setInterval(10s)` → lastReadAt が 30s 以上前なら `audioPlayer.stop()`

---

## Acceptance Criteria

1. `npm install` が成功し `node src/index.js` が起動する
2. ボットが VCに参加する際 `selfDeaf: true` が適用され 4017/close code 1000 エラーが発生しない
3. `/play <URL>` で音楽が再生される（再生中は VC で音が聞こえる）
4. `/play <キーワード>` で検索結果 5 件がボタン UI で表示され、選択後に再生される
5. `/skip` でキュー内の次の曲に進む
6. `/loop` で off → track → queue → off が切り替わる
7. `/volume 50` で音量が 50% になる
8. VC に誰もいなくなったとき自動退出する
9. `docker compose up --build` が正常起動し再生まで動作する
10. DISCORD_TOKEN が .env のみに存在しソースコードに含まれない

---

## Risks and Mitigations

| リスク | 緩和策 |
|---|---|
| @discordjs/opus のビルドが Alpine で失敗 | `opusscript` (pure JS) をフォールバックとして package.json に追加 |
| libsodium が Alpine で動作しない | `sodium-native` の代わりに `libsodium-wrappers` (pure JS) を使用 |
| yt-dlp の --get-url が遅い (2回呼び出し) | metadata 取得時に直接 URL も同時取得して 1回に統合 |
| スラッシュコマンドの 1時間キャッシュ | deploy.js を明示的に実行するか、ギルドコマンドとして登録（即時反映） |
| 既存の tests/ (pytest) が無効になる | Node.js のテストは別途 jest/vitest で書き直しが必要（今回スコープ外） |

---

## Verification Steps

1. `npm install` → exit code 0
2. `node src/deploy.js` → コマンド登録成功のログ
3. `node src/index.js` → "Bot ready" ログが出る
4. Discord で `/play https://www.youtube.com/...` → 音楽再生
5. Docker ログに 4017 や "Disconnecting from voice manually" が出ないことを確認
6. `docker compose up --build` → コンテナが正常起動

---

## Out of Scope (今回の書き直しに含まない)

- pytest テストの Node.js 移植（jest/vitest）
- `/bitrate` コマンドの権限エラーハンドリング強化
- 複数サーバーでの負荷テスト
- Slash コマンドの i18n 対応

---

*Status: pending approval — ralph または手動実装で実行してください*
