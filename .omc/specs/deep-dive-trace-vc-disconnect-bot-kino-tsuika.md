# Deep Dive Trace: vc-disconnect-bot-kino-tsuika

## Observed Result
vc-disconnect-botに機能追加を行いたい。現在のボットは5コマンド（/vc join, timer, alarm, status, cancel）を持つが、複数の実装ギャップが識別された。

## Ranked Hypotheses
| Rank | Hypothesis | Confidence | Evidence Strength | Why it leads |
|------|------------|------------|-------------------|--------------|
| 1 | Config/UX/オーケストレーションのギャップ（タイムゾーン固定・1タイマー制限・警告カスタマイズ不可等） | High | Strong | config.yamlのtimezoneキーが実行時に全く読まれていない（デッドコンフィグ）という直接証拠あり。ギルド1タイマー制限も3箇所のガードで確認。影響範囲が広い。 |
| 2 | Code-path/未実装機能分析（延長コマンドなし・bot-kickハンドリングなし・自動キャンセルなし） | High | Strong | 全てfile:line参照で直接確認。特にbot-kickによるゾンビ状態は潜在バグ。 |
| 3 | ユーザー行動/前提ミスマッチ（遅延パーミッション失敗・全員一斉切断前提） | Medium | Moderate | move_members権限チェックが起動時でなくタイマー発火時に遅延するバグは確認済み。ただし実際の被害は権限がない環境に限定。 |

## Evidence Summary by Hypothesis

### Hypothesis 1 (Config/UX)
- `timer.py:11` — `JST = ZoneInfo("Asia/Tokyo")` はモジュール定数として固定
- `config.yaml:2` — `timezone: "Asia/Tokyo"` は実行時に一切参照されない（**デッドコンフィグ**）
- 3コマンドハンドラ（`bot.py:98-104`, `148-153`, `190-195`）が `_has_active_timer` チェックでギルド2個目のタイマーをブロック
- `bot.py:65` の `_arm_timer` は `warning_seconds=_WARNING_SECONDS` 固定（ユーザー変更不可）
- `timer.py:87-89` の警告メッセージはハードコード文字列

### Hypothesis 2 (Code-path)
- `bot.py:281-288` — `on_voice_state_update` はログのみ（自動キャンセルなし）
- `bot.py:273-274` — bot-kickが無視されゾンビ状態が残存
- `timer.py:119-126` — `_disconnect_all` はシーケンシャルHTTP呼び出し（`asyncio.gather` 未使用）
- `/vc extend` コマンド・`GuildTimer.reschedule()` メソッドともに存在しない
- 単一警告しかない（多段階警告なし）

### Hypothesis 3 (行動ミスマッチ)
- `bot.py:119-122` — `perms.connect` のみチェック（`move_members` は起動時未チェック）
- タイマー発火時の `timer.py:103-134` で初めて権限エラーが発覚し、テキストチャンネルに公開エラーメッセージ（遅延失敗）
- グローバルコマンド登録（`bot.py:23` に `guild_ids` なし）だがJSTハードコード
- 単一チャンネルしか管理できない（コマンド引数でチャンネル指定不可）

## Evidence Against / Missing Evidence

- **Hypothesis 1**: CLAUDE.md が「DB不要・単純設計」を明示的に意図として記載。JST固定はJapanese-onlyサーバーには合理的。respond-before-connectパターンはDiscord APIの3秒制約により不可避。
- **Hypothesis 2**: `GuildTimer` のコンストラクタインジェクション設計により拡張点は明確。`on_complete` コールバックが既存のクリーンなフックとして機能。
- **Hypothesis 3**: `move_members` 権限を持つサーバー管理者が使う限り権限問題は発生しない。全員一斉切断は意図した設計。

## Per-Lane Critical Unknowns
- **Lane 1 (Code-path)**: bot-kickによるゾンビ状態（`_guild_states` の zombie entry + asyncio task が切断済みクライアントに対して `move_to(None)` を呼ぶ）が本番環境で実際に発生しているかどうか。
- **Lane 2 (Config/UX)**: 対象サーバーが単一VC運用（小規模コミュニティ）か複数VC並列運用（ゲーミングギルド・チームワーク）か。
- **Lane 3 (行動ミスマッチ)**: ユーザーが「機能追加」として期待しているのはUX改善か、スケールアップか、バグ修正か — 優先順位が不明。

## Lane 3 Misplacement / SoT Ownership Scope
Lane 3はファイル移動やSoT違反ではなく行動前提のミスマッチを扱うため、ownership scopeテーブルは該当なし。

## Rebuttal Round
- **Leading hypothesis**: Config/UX gaps（Hypothesis 1）— dead timezone config + single timer per guild が最も広いユーザー影響を持つ
- **Best rebuttal from Lane 2**: bot-kickゾンビ状態は潜在バグであり、機能追加より先に修正すべき可能性がある
- **Why leader held**: デッドコンフィグ（timezone）は「設定変更が効果を持たない嘘をつく設定ファイル」であり、ユーザーの信頼を損なう。1タイマー制限はアクティブに機能をブロックする。bot-kickゾンビは深刻だが発生頻度が低く、`perms.connect`チェック後にbotが正常接続できた後のシナリオに限定。

## Convergence / Separation Notes
- **Strong convergence**: Lane 1・2・3すべてが「`on_voice_state_update` が空チャンネルでタイマーをキャンセルしない」問題を独立して発見 → 最優先の新機能/修正候補
- **Partial convergence**: Lane 1とLane 2が「警告の柔軟性欠如（単一閾値・固定メッセージ）」を独立して発見
- **Separation**: Lane 3の「遅延パーミッション失敗（`perms.connect` のみ事前チェック）」はLane 1・2には現れない独自発見

## Most Likely Explanation
このボットは日本語単一サーバー向けのMVPとして設計・実装されており、基本ユースケースは正常動作する。しかし複数の技術的ギャップが蓄積している: (1) config.yamlのtimezoneキーが実行時デッドコードになっている、(2) チャンネルが自然に空になってもタイマーが自動キャンセルされない、(3) move_members権限チェックがコマンド起動時でなくタイマー発火時に遅延する、(4) タイマー延長コマンドがない。これらはMVPから次フェーズへの移行で対処すべき既知のギャップである。

## Critical Unknown
ユーザーが「機能追加」として最も期待しているのは: (a) 実用的UX改善（延長・自動キャンセル・警告カスタマイズ）か、(b) 多チャンネル・多サーバー対応（スケールアップ）か、(c) 潜在バグ修正（権限・ゾンビ状態）か — この優先順位が不明。

## Recommended Discriminating Probe
ユーザーに「今ボットを使っていて一番困っていること/欲しいと思う機能を1〜3つ挙げてください」と直接聞く。トレースで発見したギャップのうち、ユーザーが既に体験しているものと潜在的なものを分離できる。
