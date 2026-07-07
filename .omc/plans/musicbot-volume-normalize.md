# music-bot: 音量ノーマライズ機能 実装プラン

**Status:** pending approval

## Requirements Summary

`music-bot`（`/home/lemitsu/Documents/my-discord-bot/music-bot/`）に、曲ごとの音量差を吸収するラウドネスノーマライズ機能を追加する。

インタビューで確定した方針:

| 論点 | 決定事項 |
|---|---|
| 解析方式 | 事前ダウンロード + ffmpeg `loudnorm` 2パス解析（ストリーミング直接再生ではなく正確な解析を優先） |
| 設定の粒度 | ギルドごとに ON/OFF 切り替え可能。目標ラウドネス値（LUFS）は全ギルド共通の固定値 |
| 設定の永続化 | JSON ファイル（`music-bot/data/guild-settings.json`）にギルドごとの ON/OFF を保存し、再起動後も維持 |
| ダウンロードのタイミング | 現在の曲の再生中に次の曲をバックグラウンドでプリフェッチ（ダウンロード＋1パス解析）しておき、曲送り時の待ち時間を最小化 |

現状（調査済み）:
- 音声再生は `src/search.js:85` `resolveAudioStream()` が `yt-dlp -o -` の stdout をそのまま `src/player.js:64` `createAudioResource(stream, { inputType: StreamType.Arbitrary })` に渡すストリーミング方式。音量関連の実装（`/volume`、`inlineVolume`、loudnorm等）は一切存在しない。
- `music-bot/CLAUDE.md` の制約: 「yt-dlp の stdout を直接パイプする」「`--get-url` で URL を取り出して別ツールに渡すと googlevideo の認証ヘッダーが欠落してストールする」。今回はプリフェッチで **yt-dlp 自体にファイルへ直接ダウンロードさせる**（`-o <path>`、stdout パイプではない）ため、この制約に抵触しない。認証は yt-dlp が内部で解決する。
- ffmpeg / yt-dlp は Docker イメージ・ホスト両方に既にインストール済み（`Dockerfile:5`）。追加の npm 依存は不要（`child_process.spawn` で完結）。
- 永続化層・設定ストアは現状皆無（`src/sessions.js` はメモリ上のみ）。今回新規に追加する。

## Acceptance Criteria

1. `/normalize on` を実行すると、そのギルドでノーマライズが有効になり、ボット再起動後も設定が維持される（`data/guild-settings.json` に反映される）。
2. `/normalize off` で無効化でき、無効時は現状と全く同じ挙動（`resolveAudioStream` → `Arbitrary` ストリーミング再生）に戻る。
3. ノーマライズ有効時、音量が大きく異なる2曲（例: 通常音量の曲 → 過大音量の曲）を連続再生した際、体感音量がおおむね揃って聞こえる。
4. 現在の曲を再生中に、次の曲のダウンロード＋1パス解析がバックグラウンドで進行し、キューの次の曲へスキップ/自然遷移した際に無音のギャップが「プリフェッチが間に合っていれば」体感で数百ms以内に収まる（フォールバック時は同期ダウンロードになるため数秒の遅延を許容）。
5. yt-dlp ダウンロード失敗・ffmpeg 解析失敗時は、そのトラックに限り自動的に非ノーマライズ再生（既存のストリーミング方式）にフォールバックし、再生自体は継続する。
6. トラック再生終了後（自然終了・skip・stop）、そのトラック用にダウンロードした一時ファイルが削除される。ボット起動時に前回クラッシュ時の残留一時ファイルもクリーンアップされる。
7. 30分を超える長尺トラック（デフォルト値、要調整可）はノーマライズをスキップし既存のストリーミング再生にフォールバックする（ダウンロード容量・解析時間の暴走防止）。
8. `npm test` で新規追加した純粋ロジック（loudnorm JSON パース、設定ファイルの読み書き）のユニットテストがパスする。
9. `docker compose up --build` で `data/` ディレクトリがコンテナ再作成後も設定を保持する（ボリュームマウント経由）。

## Implementation Steps

### 1. `src/settings.js`（新規）— ギルド設定の永続化
- `loadSettings()` / `getGuildSettings(guildId)` / `setNormalize(guildId, enabled)` を実装。
- 起動時に `data/guild-settings.json` を読み込みメモリの `Map<guildId, { normalize: boolean }>` にキャッシュ。ファイルが存在しない場合は空オブジェクトから開始（デフォルト `normalize: false`）。
- 書き込みは `fs.writeFile` で一時ファイル→`rename` のアトミック書き込みにし、破損を防ぐ。
- `data/` ディレクトリが無ければ起動時に作成（`fs.mkdir(recursive: true)`）。

### 2. `src/normalize.js`（新規）— ダウンロード・解析・再生資源生成
- `downloadAudio(url, destPath)`: `spawn('yt-dlp', ['-f', 'bestaudio/best', '--no-playlist', '-o', destPath, url])` の完了を待つ Promise。失敗時は例外。
- `analyzeLoudness(filePath)`: `spawn('ffmpeg', ['-i', filePath, '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'])` を実行し、stderr末尾のJSONブロック（`measured_I`, `measured_TP`, `measured_LRA`, `measured_thresh`, `input_i` 等）をパースして返す純粋関数 `parseLoudnormJson(stderrText)` を分離しユニットテスト可能にする。
- `createNormalizedResource(filePath, measured)`: 2パス目として `ffmpeg -i filePath -af loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=...:measured_TP=...:measured_LRA=...:measured_thresh=...:offset=...:linear=true:print_format=summary -f s16le -ar 48000 -ac 2 pipe:1` を spawn し、`createAudioResource(proc.stdout, { inputType: StreamType.Raw })` を返す。同一 ffmpeg プロセス内でフィルタ＋PCMエンコードを完結させ、`@discordjs/voice` 側の二重 ffmpeg 起動を避ける。
- `prefetchTrack(track)`: 一時ファイルパスを発行 → `downloadAudio` → `analyzeLoudness` を行い、結果 `{ filePath, measured }` を返す非同期関数。エラー時は一時ファイルを削除して例外を再送出。
- `cleanupTempFile(filePath)`: 存在すれば削除（`fs.rm`、ENOENT無視）。
- `cleanupStaleTempDir()`: 起動時に一時ディレクトリ（`path.join(os.tmpdir(), 'music-bot-normalize')`）内の残留ファイルを全削除。
- 長尺トラックガード: `MAX_NORMALIZE_DURATION_SEC = 1800` を超える `track.duration` はプリフェッチ対象外とする定数・判定関数をここに置く。

### 3. `src/player.js` — 再生パイプラインの分岐とプリフェッチ連携
- `GuildPlayer` にプリフェッチ結果を保持する内部状態（`#prefetchPromise`、対象トラック参照）を追加。トラックオブジェクト参照をキーにする（`queue.js` の `#tracks` 配列は同一オブジェクト参照を保持するため、位置変更 [shuffle/move] に影響されない）。
- `playNext()`:
  - ギルド設定 (`settings.getGuildSettings(guildId).normalize`) を確認。
  - 無効、または対象トラックが長尺ガード対象、またはプリフェッチ/同期処理が失敗した場合 → 既存の `resolveAudioStream` + `Arbitrary` パスに**フォールバック**（変更なし）。
  - 有効時: 直前にプリフェッチが該当トラックに対して開始されていればその Promise を await（間に合っていれば即座に resolve）。開始されていなければ（キュー先頭の初回再生など）その場で同期的に `prefetchTrack` を実行してから再生。
  - 再生開始後、`queue.upcoming()[0]` が存在し正規化対象条件を満たせば、非同期で次トラックの `prefetchTrack` を発火し `#prefetchPromise` に保持（await はしない、fire-and-forget）。
  - 例外は catch し、ログ出力の上で非ノーマライズ再生にフォールバック（Acceptance Criteria 5）。
- `#handleAfter()` / `skip()` / `stop()`: 再生し終えた（または中断した）トラックに紐づく一時ファイルを `cleanupTempFile` で削除。次トラックのプリフェッチが進行中に skip された場合は、そのプリフェッチ結果が新しい `current` と一致するか確認し、一致しなければ完了を待って cleanup する（迷子ファイル防止）。

### 4. `src/commands/normalize.js`（新規）— スラッシュコマンド
- `bitrate.js` / `loop.js` の書式に合わせる。`SlashCommandBuilder` に `.addBooleanOption('enabled')` （必須）。
- VC 参加チェックは既存コマンドと異なりギルド全体設定なので `checkSameVoiceChannel` は不要（再生中でなくても設定変更できるようにする）。
- 実行時 `settings.setNormalize(interaction.guildId, enabled)` を呼び、`✅ ノーマライズを **有効/無効** にしました` を ephemeral 返信。

### 5. `src/deploy.js` / コマンドロード
- `src/index.js` の既存コマンドロードは `src/commands/` ディレクトリを走査する方式（要確認・既存パターンに追従するだけで新規ファイル追加のみで自動登録される想定）。`node src/deploy.js` の再実行が必要な旨を運用メモに残す。

### 6. Docker / 永続化
- `docker-compose.yml` に `volumes: - ./data:/app/data` を追加し、`data/guild-settings.json` をホスト側に永続化。
- `Dockerfile` は変更不要（ffmpeg 済みインストール、`data/` はランタイムで自動作成）。

### 7. テスト（`node --test`、既存 `queue.test.js` と同じ規約）
- `src/normalize.test.js`: `parseLoudnormJson` の正常系・異常系（不正JSON、欠損フィールド）、長尺ガード判定関数。
- `src/settings.test.js`: 一時ディレクトリを使い、`setNormalize` → 再読込 で値が復元されること、ファイル未存在時のデフォルト値、アトミック書き込みで壊れないこと。
- ffmpeg/yt-dlp の実プロセス起動を伴う `downloadAudio`/`analyzeLoudness`/`prefetchTrack` は外部コマンド依存のため単体テスト対象外とし、手動検証（Verification Steps）でカバーする。

## Risks and Mitigations

| リスク | 対策 |
|---|---|
| プリフェッチ中は現トラック再生とダウンロード/解析が並走し、CPU・帯域を一時的に倍増させる | 単一トラック分のみの先行プリフェッチに限定（キュー全体の先読みはしない）。長尺トラックは対象外に。 |
| ダウンロード先の一時ファイルが再生前にスキップ・キュー編集で不要になり肥大化 | 曲終了/skip/stop 時に必ず cleanup。起動時に残留ファイルを一括削除するセーフティネットを追加。 |
| yt-dlp ダウンロードや ffmpeg 解析が失敗（動画削除・地域制限等） | 例外を catch し、そのトラックのみ既存ストリーミング方式にフォールバック。再生停止させない。 |
| JSON設定ファイルへの同時書き込みで破損 | 一時ファイル→rename のアトミック書き込みにする。 |
| Docker コンテナ再作成で `data/` が消える | `docker-compose.yml` にバインドマウントを追加。 |
| loudnorm の 2パス目 (`linear=true`) がクリッピングする曲がある | `TP=-1.5`（true peak）を設定し、ffmpeg 側のリミッタで overshoot を抑制。これは業界標準の設定値であり追加対応不要。 |

## Verification Steps

1. `npm test`（`music-bot/` 内）で新規テストを含め全テストがパスすること。
2. ローカルでボット起動 → `/normalize on` → 音量差の大きい2曲を連続再生 → 体感音量が揃うことを確認。
3. `/normalize off` → 同じ2曲で従来通り音量差が出ることを確認（回帰なし）。
4. ボット再起動後、`/normalize` の設定（ON/OFF）が保持されていることを確認。
5. 現在の曲再生中にログ（`console.log`等の一時デバッグ出力）で次曲のプリフェッチが開始されていることを確認し、曲送り時のギャップが短いことを確認。
6. わざと存在しない/削除済み動画URLをキューに入れてノーマライズ有効時にエラーフォールバックが発生し、再生が止まらないことを確認。
7. 再生終了後に一時ディレクトリ（`os.tmpdir()/music-bot-normalize`）にファイルが残っていないことを確認。
8. `docker compose up --build` 後、コンテナを再作成しても `/normalize` 設定が保持されることを確認。

## Open Assumptions (要合意事項)

- ノーマライズの**デフォルト値は OFF**（既存ギルドの挙動を変えないため）。異なるデフォルトを希望する場合は変更可能。
- 目標ラウドネスは `I=-16 LUFS, TP=-1.5dB, LRA=11`（Discord/一般的な配信基準に近い値）で固定。
- 長尺ガードのしきい値は 30分とする（暫定値、必要に応じて調整可能）。
