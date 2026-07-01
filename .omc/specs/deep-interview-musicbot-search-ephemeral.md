# Deep Interview Spec: Music Bot 検索UI整理 + Ephemeral表示ポリシー

## Metadata
- Interview ID: musicbot-search-ephemeral-2026-06-30
- Rounds: 4
- Final Ambiguity Score: 12.5%
- Type: brownfield
- Generated: 2026-06-30
- Threshold: 0.2
- Threshold Source: default
- Initial Context Summarized: no
- Status: PASSED

## Clarity Breakdown
| 次元 | スコア | 重み | 加重 |
|------|--------|------|------|
| Goal Clarity | 0.92 | 0.35 | 0.322 |
| Constraint Clarity | 0.88 | 0.25 | 0.220 |
| Success Criteria | 0.88 | 0.25 | 0.220 |
| Context Clarity | 0.88 | 0.15 | 0.132 |
| **Total Clarity** | | | **0.894** |
| **Ambiguity** | | | **10.6%** |

## Topology
| コンポーネント | 状態 | 説明 | カバレッジ |
|--------------|------|------|-----------|
| Search UI cleanup | active | 検索結果選択後にチャットを整理する | ephemeral検索パネル→選択後削除→公開キュー追加通知 |
| Ephemeral display policy | active | コマンド別の公開/個人表示を定義する | 12コマンドすべてに適用 |

## Goal
`/play キーワード` の検索フローを以下に変更する:
1. 検索パネルを ephemeral（本人のみ表示）で表示する
2. ボタン選択後、その ephemeral メッセージを削除する
3. キュー追加完了を全体公開メッセージで通知する

加えて、全コマンドの返信を以下のポリシーで公開/個人表示に分類する。

## 制約 (Constraints)
- Discordの ephemeral メッセージは `flags: MessageFlags.Ephemeral` で設定する
- 検索パネルの削除は `interaction.deleteReply()` を使用（元インタラクションを `pendingStore` に保存する必要あり）
- ephemeral メッセージの削除は元インタラクショントークンが有効な15分以内に実行される前提
- `@discordjs/voice` 等の音声実装は変更しない
- LLM・外部AI API は使用しない（既存制約）

## Non-Goals
- `/play URL`（URL直接再生）のフロー変更はしない（既にキュー追加成功を1メッセージで完結）
- 音声再生ロジック・ウォッチドッグ・ループ処理の変更
- 新コマンドの追加

## 公開/Ephemeral 表示ポリシー

### 全体公開（Public）にするコマンド・メッセージ
| メッセージ | コマンド | 備考 |
|-----------|---------|------|
| ✅ キューに追加しました: **曲名** (時間) | /play URL | URL直接再生時 |
| ✅ キューに追加しました: **曲名** (時間) | /play キーワード → 選択後 | 検索→選択後の通知 |
| キュー一覧 | /queue | 再生中・次の曲リスト |
| スキップ通知 | /skip | 操作通知 |
| 停止通知 | /stop | 操作通知 |
| 一時停止通知 | /pause | 操作通知 |
| 再開通知 | /resume | 操作通知 |

### Ephemeral（本人のみ）にするコマンド・メッセージ
| メッセージ | コマンド |
|-----------|---------|
| 🔍 検索結果: (ボタンUI) | /play キーワード |
| 現在再生中の曲情報 | /nowplaying |
| ループモード変更 | /loop |
| 音量変更 | /volume |
| シャッフル実行 | /shuffle |
| ビットレート変更 | /bitrate |
| VC切断通知 | /leave |
| すべてのエラーメッセージ | 全コマンド共通 |

## Acceptance Criteria
- [ ] `/play キーワード` 実行時、検索パネルが自分にしか見えない（ephemeral）
- [ ] 検索パネルのボタンを押すと、そのephemeralメッセージが消える
- [ ] ボタン選択後、チャット全体に「✅ キューに追加しました: **曲名** (時間)」が投稿される
- [ ] `/play URL` の動作は変更なし（公開の「✅ キューに追加しました」）
- [ ] `/queue` は公開メッセージのままで表示される
- [ ] `/skip` `/stop` `/pause` `/resume` は公開メッセージ
- [ ] `/nowplaying` `/loop` `/volume` `/shuffle` `/bitrate` `/leave` はephemeral
- [ ] エラーメッセージはすべてephemeral（既存動作の一部は既にephemeral）
- [ ] VC未参加エラーなどの既存ephemeralは維持

## Technical Context
### 変更ファイル
- `src/commands/play.js` — 検索フロー変更（deferReply ephemeral + pendingStoreに元interactionも保存）
- `src/sessions.js` — `pendingStore.set()` シグネチャ変更（元interactionを追加保存）
- `src/views.js` — `SearchPendingStore.set()` インターフェース拡張
- `src/commands/nowplaying.js` — ephemeral化
- `src/commands/loop.js` — ephemeral化
- `src/commands/volume.js` — ephemeral化
- `src/commands/shuffle.js` — ephemeral化
- `src/commands/bitrate.js` — ephemeral化
- `src/commands/leave.js` — ephemeral化
- `src/commands/skip.js` — 確認（現在の公開状態を維持）
- `src/commands/stop.js` — 確認（現在の公開状態を維持）
- `src/commands/pause.js` — 確認（現在の公開状態を維持）
- `src/commands/resume.js` — 確認（現在の公開状態を維持）
- `src/commands/queue.js` — 確認（現在の公開状態を維持、空時のephemeralは維持）

### 実装方針: 検索フロー
```
現在:
interaction.deferReply()                           // 公開defer
→ followUp({ content: '🔍 検索結果:', components }) // 公開メッセージ
→ ボタンclick: deferUpdate() → followUp('✅ キューに追加') // 新公開メッセージ

変更後:
interaction.deferReply({ ephemeral: true })         // ephemeral defer
→ interaction.editReply({ content: '🔍 検索結果:', components }) // ephemeralパネル
→ pendingStore.set(msg.id, results, onSelect, interaction) // 元interactionも保存
→ ボタンclick: deferUpdate()
→ onSelect内: interaction.deleteReply()            // ephemeralパネル削除
             + originalInteraction.followUp('✅ キューに追加') // 公開通知
```

### 注意事項
- `interaction.deferReply({ ephemeral: true })` の後 `interaction.editReply()` でephemeralパネルを表示
- ボタンインタラクションの `deferUpdate()` 後、元コマンドインタラクション（`originalInteraction`）の `deleteReply()` でephemeralを削除
- `originalInteraction.followUp(...)` は flags なしで公開メッセージとして投稿

## Interview Transcript
<details>
<summary>Full Q&A (4 rounds)</summary>

### Round 0 (Topology)
**Q:** 2コンポーネント構成は正しいか？
**A:** 合っている（2つとも実装）

### Round 1
**Q:** 全体公開にしたいコマンドはどれか？
**A:** キュー関連 + 操作通知を公開（/play追加通知、/queue、/skip、/stop、/pause、/resume）

### Round 2
**Q:** 検索結果パネルの選択後、どう編集するか？
**A:** ✅ 選択: **曲名** に内容変更＋ボタン削除（→ Round 3で「削除」に変更）

### Round 3
**Q:** 選択後のメッセージはどうするか？
**A:** 自動削除で、キュー追加のメッセージが全体に送信される

### Round 4
**Q:** 検索パネルの初期表示はephemeralか公開か？
**A:** ephemeral（本人のみ）

</details>
