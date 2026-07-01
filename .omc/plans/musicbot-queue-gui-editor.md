# music-bot: キュー編集 GUI 化計画

**Status:** pending approval
**対象:** `music-bot/` (Discord.js v14)

## 要件サマリー

`/queue` コマンドの出力をプレーンテキストから、Discord のメッセージコンポーネント（StringSelectMenu + Button + Modal）を使った視覚的な編集 UI に置き換える。

ヒアリングで確定した仕様:

| 項目 | 決定内容 |
|---|---|
| UI 方式 | セレクトメニュー(曲選択) + 操作ボタン(移動・削除) |
| サポート操作 | 削除 / 上下に1つ移動 / 次に再生(先頭へ) / 任意の位置へジャンプ移動 |
| 操作権限 | Bot と同じボイスチャンネルにいる全員 |
| 表示方式 | パブリック表示（チャンネルに1つの共有メッセージ、VC内の誰でも操作可） |
| 対象範囲 | 「次の曲」リスト(`upcoming()`)のみ。現在再生中のトラックは編集対象外 |
| エントリポイント | 既存の `/queue` コマンドを置き換え（新規コマンドは追加しない） |

## 設計判断

- **状態管理はステートレス（custom_id エンコード方式）を採用**。既存の `SearchPendingStore`（`src/views.js:31-45`）のような Map ベースのストアは、メッセージ ID をキーにした状態が Bot 再起動で失われる／エントリの掃除が必要という弱点がある。ページ番号と選択中インデックスを `custom_id` 文字列に埋め込むことで、サーバー側状態を一切持たずに再描画できる。custom_id は 100 文字制限があるが、埋め込むのは小さい整数2つのみなので十分収まる。
- **移動先ジャンプは Modal (TextInputBuilder) で数値入力**。選択方式のUIパラダイムからは外れるが、キューが長い場合に「移動先」をセレクトメニューで選ばせると2段階選択+ページ跨ぎの複雑さが増すため、数値直接入力の方が実装・UXともに単純。
- **アクションボタン行は選択がある時のみ表示**し、明示的な「選択解除」ボタンは設けない（ページ送り操作で選択は自動的にクリアされるため）。ActionRow の5ボタン上限（↑/↓/⏭/🎯/🗑）にちょうど収まる。
- **ページ送りインジケータはボタンではなく Embed footer** に表示（例: `ページ 2/5`）し、ボタン枠を節約する。
- **編集対象は upcoming のみ**。現在再生中のトラックを削除・移動できるようにすると `player.js` のウォッチドッグ/再生ロジックとの整合性を壊すリスクが高く、要件にも「次に再生」止まりで「現在再生中の差し替え」は含まれていない。

## 実装ステップ

### 1. `src/queue.js` — `GuildQueue` に編集用メソッドを追加

`upcoming()`（既存, line 64-67）を基準にした相対インデックスで操作する。絶対インデックス変換は private ヘルパーに閉じ込め、外部からは `#tracks` を直接触らせない（既存のカプセル化方針を踏襲）。

```js
#upcomingToAbsolute(upcomingIndex) {
  const abs = this.#currentIndex + 1 + upcomingIndex;
  if (upcomingIndex < 0 || abs >= this.#tracks.length) return null;
  return abs;
}

removeUpcoming(upcomingIndex) {
  const abs = this.#upcomingToAbsolute(upcomingIndex);
  if (abs === null) return false;
  this.#tracks.splice(abs, 1);
  return true;
}

moveUpcoming(fromIndex, toIndex) {
  const len = this.upcoming().length;
  if (fromIndex < 0 || fromIndex >= len || toIndex < 0 || toIndex >= len || fromIndex === toIndex) return false;
  const absFrom = this.#currentIndex + 1 + fromIndex;
  const absTo = this.#currentIndex + 1 + toIndex;
  const [track] = this.#tracks.splice(absFrom, 1);
  this.#tracks.splice(absTo, 0, track);
  return true;
}
```

`moveUpcoming` 1つで「上へ」(`toIndex = fromIndex - 1`)、「下へ」(`toIndex = fromIndex + 1`)、「次に再生」(`toIndex = 0`)、「任意の位置へ」(`toIndex` = ユーザー入力-1) をすべて表現できる。

### 2. `src/queueEditorView.js`（新規）— 編集 UI のレンダリング

- `PAGE_SIZE = 10`（既存 `commands/queue.js:32` の `slice(0, 10)` を踏襲）
- `buildQueueEditorPayload(queue, { page = 0, selectedIndex = null })` → `{ embeds, components }`
  - Embed: `再生中` フィールド + 現在ページの upcoming リスト（絶対 upcoming index を番号表示、選択中の曲は `▶` 等で強調）+ footer に `ページ X/Y` + ループ状態
  - upcoming が 0 件のページ（キュー空 or 再生中のみ）→ StringSelectMenu は省略し「次の曲はありません」テキストのみ
  - Row1: `StringSelectMenuBuilder`（customId: `qedit_select_p${page}`, options: 現在ページの曲、value = upcoming index 文字列, label/description は既存 `views.js` と同様に80文字丸め）※ options が 0 件の場合は行ごと省略（Discord は空 SelectMenu を許可しない）
  - Row2: ページ送りボタン `qedit_page_p${page-1}`（前へ）/ `qedit_page_p${page+1}`（次へ）、境界で `disabled: true`
  - Row3（`selectedIndex != null` の時のみ）: `qedit_moveup_p${page}_i${selectedIndex}` / `qedit_movedown_p${page}_i${selectedIndex}` / `qedit_tofront_p${page}_i${selectedIndex}` / `qedit_jump_p${page}_i${selectedIndex}` / `qedit_remove_p${page}_i${selectedIndex}`

### 3. `src/queueEditorInteractions.js`（新規）— インタラクション処理

`handleQueueEditorInteraction(interaction, sessions)` をエクスポートし、`customId` が `qedit_` で始まるすべての Button / StringSelectMenu / ModalSubmit インタラクションを扱う。

共通の前処理:
1. `session = sessions.get(interaction.guildId)`。存在しない/`queue.isEmpty` なら ephemeral エラーで打ち切り。
2. 権限チェック: `interaction.member.voice.channelId === session.connection.joinConfig.channelId`（`src/index.js:63` と同じ参照パターン）。不一致なら ephemeral `❌ 同じボイスチャンネルに参加してから操作してください`。
3. `customId` を `_p(\d+)(?:_i(\d+))?` でパースして page / selectedIndex を復元。

分岐:
- **StringSelectMenu** (`qedit_select_p*`): 選択された value (upcomingIndex) を selectedIndex として再描画 → `interaction.update(buildQueueEditorPayload(...))`
- **ページ送りボタン** (`qedit_page_p*`): 新ページで selectedIndex なしで再描画
- **移動系ボタン** (`qedit_moveup` / `qedit_movedown` / `qedit_tofront`): `queue.moveUpcoming` を呼び、成功なら選択を維持(moveIndexも追従移動) or 解除して再描画。呼び出し前に `selectedIndex` が現在の `upcoming().length` の範囲内か再検証（他ユーザーが並行編集した場合の防御）。範囲外なら ephemeral `⚠️ キューが変更されました。もう一度選択してください` + 現在の状態で再描画。
- **削除ボタン** (`qedit_remove`): `queue.removeUpcoming`。削除後にページが範囲外になった場合は `page = min(page, maxPage)` にクランプ。
- **ジャンプボタン** (`qedit_jump`): `interaction.showModal(...)` で `TextInputBuilder`（customId: `qedit_jumpmodal_p${page}_i${selectedIndex}`, style: Short, 数値のみ許可のバリデーションはサブミット時に実施）
- **ModalSubmit** (`qedit_jumpmodal_p*`): 入力値をパースし `1 <= n <= upcoming().length` を検証（範囲外は ephemeral エラー）、`toIndex = n - 1` で `moveUpcoming` を実行し再描画

すべての再描画は `queue` から都度フレッシュに `upcoming()` / `current` を読み直す（キャッシュしない）ことで、複数ユーザーの並行操作による表示ズレを最小化する。

### 4. `src/index.js` — ディスパッチ追加

`InteractionCreate` ハンドラ（現状 line 28-55）に以下を追加。既存の `search_` ボタン処理（line 46-54）と同様の分岐を増やすと肥大化するため、`qedit_` プレフィックスのインタラクションは丸ごと委譲する:

```js
if (interaction.customId?.startsWith('qedit_')) {
  return handleQueueEditorInteraction(interaction, sessions)
}
```

`isStringSelectMenu()` / `isButton()` / `isModalSubmit()` のいずれであっても `customId` は共通で判定できるため、上記1行で3種類のインタラクションをまとめて委譲できる。

### 5. `src/commands/queue.js` — コマンド本体の置き換え

現状の line 21-37（テキスト整形して `interaction.reply(lines.join('\n'))`）を、`buildQueueEditorPayload(session.queue, { page: 0 })` を呼んで `interaction.reply({ embeds, components })` に置き換える。空キュー時の ephemeral エラー（line 23-24）はそのまま維持。

## リスクと対策

| リスク | 対策 |
|---|---|
| 複数ユーザーの同時編集で表示と実キューがズレる | 操作実行の直前に selectedIndex/page を再検証し、ズレていれば ephemeral 警告＋最新状態で再描画（ステップ3参照） |
| 現在再生中のトラックを誤って操作対象にしてしまう | upcoming 相対インデックスのみを扱い、`#currentIndex` 以前には絶対に触れない設計にする |
| Discord の StringSelectMenu は最小1オプション必須 | upcoming が0件のページでは SelectMenu 自体を省略するレンダリング分岐を必須にする |
| custom_id の桁あふれ・不正パース | ページ番号/インデックスは整数のみを許可する正規表現でパースし、マッチ失敗時は無視（no-op）にする |
| 曲タイトルの絵文字/長文で SelectMenu の label(100字)/description(100字) 上限超過 | `views.js` の既存 `.slice(0, 80)` パターンを踏襲して丸める |
| `GuildQueue` の新メソッドにバグがあると再生中の曲を巻き込む | ステップ「テスト」でユニットテストにより `#currentIndex` 前後の境界条件を検証 |

## テスト・検証ステップ

1. **ユニットテスト（新規）**: `music-bot/src/queue.test.js` を Node 標準の `node:test` + `node:assert`（Node20 で追加依存なしに使える）で作成し、`GuildQueue` の `removeUpcoming` / `moveUpcoming` を以下の観点で検証する:
   - 空キュー・upcoming 0件での no-op（false を返す）
   - 範囲外インデックス（負数、`upcoming().length` 以上）での no-op
   - 先頭への移動（`toIndex=0`）で `next()` 時に正しい曲が再生されること
   - 削除後も `#currentIndex` が指す現在再生中トラックが変化しないこと
   - `package.json` の `scripts` に `"test": "node --test src/"` を追加
   - 実行: `cd music-bot && npm test`
2. **手動 E2E 確認**（実際の Discord サーバーで実施、Bot 起動が必要）:
   - `/play` で3曲以上キューに積んだ状態で `/queue` を実行し、Embed + SelectMenu + ページングボタンが表示されることを確認
   - 曲を選択 → 操作ボタン行が表示される → 「↑」「↓」でキュー順が入れ替わることを `/nowplaying` や再度の `/queue` で確認
   - 「次に再生」実行後に `/skip` し、選択した曲が実際に次に再生されることを確認
   - 「任意の位置へ」でモーダルに範囲外の数値・非数値を入力してエラーになることを確認
   - 「削除」実行後、リストから消え、再生中の曲に影響がないことを確認
   - 別ユーザー（VC参加者）が同じメッセージのボタンを操作できることを確認
   - VC外のユーザーが操作しようとすると ephemeral エラーになることを確認
   - 11曲以上キューに積んでページングが機能することを確認

## 変更ファイル一覧

- `music-bot/src/queue.js` — `removeUpcoming` / `moveUpcoming` 追加
- `music-bot/src/queueEditorView.js` — 新規、Embed/コンポーネント生成
- `music-bot/src/queueEditorInteractions.js` — 新規、インタラクションハンドラ
- `music-bot/src/index.js` — `qedit_` ディスパッチ追加
- `music-bot/src/commands/queue.js` — テキスト応答をGUI応答に置き換え
- `music-bot/src/queue.test.js` — 新規、ユニットテスト
- `music-bot/package.json` — `test` スクリプト追加
