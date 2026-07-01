# music-bot: シャッフル時に再生済み曲を復活させないようにする

**Status:** pending approval

## Requirements Summary

`/shuffle` コマンド実行時、現在再生中の曲より前（＝再生済み）のトラックまでシャッフル対象に含まれてしまい、シャッフル後に再生済み曲がキューの待機列（`currentIndex` より後ろ）に紛れ込んで再度再生されることがある。再生済み曲はシャッフル対象・待機列から除外し、**現在再生中の曲より後ろ（待機中）のトラックのみ**をシャッフルするように修正する。

## Root Cause

`music-bot/src/queue.js:30-39` の `GuildQueue#shuffle()`:

```js
shuffle() {
  if (this.#currentIndex < this.#tracks.length) {
    const current = this.#tracks.splice(this.#currentIndex, 1)[0];
    for (let i = this.#tracks.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [this.#tracks[i], this.#tracks[j]] = [this.#tracks[j], this.#tracks[i]];
    }
    this.#tracks.splice(this.#currentIndex, 0, current);
  }
}
```

- 現在再生中の1曲だけを配列から取り除き、**残り全体**（インデックス `0..currentIndex-1` の再生済み曲 + `currentIndex+1..end` の未再生曲）をシャッフルしている。
- シャッフル後、再生済み曲が `currentIndex` より後ろの位置に来る可能性があり、`next()`（`#currentIndex += 1` で単純に進める実装、`queue.js:48-64`）がその曲を「次の曲」として再生してしまう＝再生済み曲の「復活」。

## Acceptance Criteria

- [ ] `shuffle()` 実行後、`#tracks[0..currentIndex]`（再生済み曲 + 現在再生中の曲）の**内容と順序**が実行前と完全に一致する。
- [ ] `shuffle()` 実行後、`#tracks[currentIndex+1..end]`（待機中の曲）の**集合**は実行前と同じだが、順序はランダムに並び替わっている（要素の追加・削除・重複がない）。
- [ ] 待機中トラックが0〜1件の場合、`shuffle()` は例外を投げず何もしない（現状の `if (this.#currentIndex < this.#tracks.length)` 相当のガードを維持）。
- [ ] `/shuffle` コマンド (`src/commands/shuffle.js`) の呼び出し側インターフェースは変更不要（`session.queue.shuffle()` のシグネチャ据え置き）。
- [ ] 既存の `LoopMode`（OFF/TRACK/QUEUE）や `next()` の挙動に影響を与えない。

## Implementation Steps

1. `music-bot/src/queue.js` の `shuffle()` を書き換え、再生済み区間（`0..currentIndex`）には触れず、`currentIndex + 1` 以降の待機列だけを Fisher–Yates でシャッフルする。

   ```js
   shuffle() {
     const start = this.#currentIndex + 1;
     if (start >= this.#tracks.length) return;
     for (let i = this.#tracks.length - 1; i > start; i--) {
       const j = start + Math.floor(Math.random() * (i - start + 1));
       [this.#tracks[i], this.#tracks[j]] = [this.#tracks[j], this.#tracks[i]];
     }
   }
   ```

   - 現在の実装のように一時配列へ `splice` して抜き出す必要がなくなり、再生済み区間は一切変更されない。
   - 未再生区間のみを対象にした Fisher–Yates シャッフル（`start` オフセット付き）。

2. 動作確認用の簡易スクリプトまたは手動デバッグで、以下を検証する:
   - `#tracks` に 6曲、`#currentIndex = 2`（再生済み2曲 + 現在再生中1曲、残り3曲待機）の状態を作り、`shuffle()` 呼び出し前後で `#tracks.slice(0, 3)`（再生済み+現在）が完全一致すること、`#tracks.slice(3)` の集合が変わらないことを確認。
   - `#currentIndex` が最後の要素（待機曲なし）の場合に `shuffle()` が何もしないこと。

## Risks and Mitigations

| リスク | 対策 |
|---|---|
| Fisher–Yates のオフセット計算を誤ると待機列以外を巻き込む | 実装後に手動デバッグスクリプトで境界（`start-1` と `start` の要素）が変化しないことを明示的に確認する |
| `#tracks` はプライベートフィールドのためユニットテストからのアクセスが難しい（`npm test` スクリプト自体が未整備） | `node -e` または一時的なデバッグスクリプトで `GuildQueue` をインポートして直接検証する（`package.json` に test script なし、既存踏襲） |

## Verification Steps

1. `music-bot/src/queue.js` の diff レビュー。
2. Node ワンショットスクリプトで `GuildQueue` を生成し、`add()` でモックトラックを複数投入 → `next()` を数回呼んで `#currentIndex` を進める → `shuffle()` 実行 → `current` と `upcoming()` の中身を出力して、再生済み分が動いていないこと・待機分の集合が保たれていることを確認。
3. （可能であれば）実機 Discord での `/play` 複数曲 → 数曲スキップ → `/shuffle` → `/queue` 相当のUIで再生済み曲が復活しないことを目視確認。

## ADR（簡易）

- **Decision**: `shuffle()` の対象範囲を `currentIndex+1` 以降の待機列のみに限定する。
- **Drivers**: 再生済み曲の「復活」バグ解消、既存の呼び出し側APIとの互換性維持。
- **Alternatives considered**:
  - (a) 再生済み曲を配列から都度削除する設計に変更 → `LoopMode.QUEUE`（キュー全体ループ）が再生済み履歴に依存する可能性があり、`next()` の既存ロジックへの影響範囲が広いため見送り。
  - (b) 現状のように一旦 `current` を抜き出して全体シャッフル後に再挿入する方式を維持しつつ範囲を絞る → 待機列だけを操作するほうがシンプルで副作用が少ないため不採用。
- **Why chosen**: 最小差分で `#tracks` のインデックス構造（`currentIndex` ベースの履歴/現在/未来管理）を壊さずにバグを修正できる。
- **Consequences**: `shuffle()` の計算量は変わらず O(n)。既存の `upcoming()` / `next()` はそのまま動作する。
- **Follow-ups**: なし（スコープ外）。テストフレームワーク未整備の状態は本修正の範囲外。
