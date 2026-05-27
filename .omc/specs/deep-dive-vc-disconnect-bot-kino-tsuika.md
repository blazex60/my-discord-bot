# Feature Spec: vc-disconnect-bot 機能追加

**Interview ID:** c7a2f3e1-4b8d-4c9a-b5e2-1f0d3a7e6c84
**Ambiguity at crystallization:** ~15%
**Trace path:** `.omc/specs/deep-dive-trace-vc-disconnect-bot-kino-tsuika.md`

---

## Goal

vc-disconnect-bot に以下の4つの機能群を追加する:
1. **複数VC同時タイマー** — 同一ギルド内の複数VCに独立したタイマーを同時設定できるようにする
2. **空チャンネル自動停止** — 全人間メンバーがVCから退出したらタイマーを自動キャンセルしてボットも退出する
3. **特定ユーザー即時切断/タイマー切断** — @メンションで指定したユーザーのみを即時または N分後に切断する
4. **VCチャンネル間移動** — 特定ユーザーまたは全員を別のVCチャンネルへ即時移動する

---

## New Commands

| コマンド | 説明 | 例 |
|---|---|---|
| `/vc kick <user1> [user2...]` | 指定ユーザーを即時切断 | `/vc kick @Alice @Bob` |
| `/vc kick-timer <minutes> <user>` | N分後に指定ユーザーを切断 | `/vc kick-timer 30 @Alice` |
| `/vc move <user> <channel>` | 指定ユーザーを別VCへ移動 | `/vc move @Alice #lobby` |
| `/vc move-all <channel>` | 現在VCの全員を別VCへ移動 | `/vc move-all #lobby` |

### 既存コマンド変更

| コマンド | 変更内容 |
|---|---|
| `/vc timer <minutes>` | 呼び出し元が居るVC個別にタイマーを設定（複数VC同時可） |
| `/vc alarm <HH:MM>` | 呼び出し元が居るVC個別にアラームを設定（複数VC同時可） |
| `/vc status` | 呼び出し元が居るVCのタイマー状態のみ表示 |
| `/vc cancel` | 呼び出し元が居るVCのタイマーのみキャンセル |
| `/vc join` | 変更なし |

---

## Constraints

- **Python 3.12+、py-cord** — 既存の技術スタックを維持
- **DB不要** — 状態はインメモリのみ（再起動でリセット仕様を維持）
- **@メンションで対象指定** — `/vc kick`・`/vc move` はロール指定不要
- **ボットのVC入居は任意** — 複数VCタイマー管理においてボット自身がVCに入居しなくてもよい
- **`Move Members` 権限が必要** — これは維持する
- **ボットはギルドに1インスタンス** — 複数ボットインスタンスは使わない

---

## Non-Goals

- タイマーの永続化（再起動後もタイマーを維持）
- ロールベースの切断免除（VIP/管理者を除外する機能）
- 多段階警告（10分前・5分前・1分前 etc.）
- 警告メッセージ文言のカスタマイズ

---

## Acceptance Criteria

### AC-1: 複数VC同時タイマー
- [ ] `#vc-A` のメンバーが `/vc timer 30` を実行すると `#vc-A` にタイマーが設定される
- [ ] 同時に `#vc-B` のメンバーが `/vc timer 60` を実行できる（既存タイマーがあってもブロックされない）
- [ ] `/vc status` は呼び出し元が居るVCのタイマー状態のみ返す
- [ ] `/vc cancel` は呼び出し元が居るVCのタイマーのみキャンセルする（他VC影響なし）
- [ ] 各タイマーは独立して発火し、互いに干渉しない

### AC-2: 空チャンネル自動停止
- [ ] 全人間メンバーが対象VCから退出すると、そのVCのタイマーが自動キャンセルされる
- [ ] 自動キャンセル時にテキストチャンネルへ通知メッセージを送信する
- [ ] ボットが対象VCに入居していた場合は合わせて退出する

### AC-3: 即時切断 (`/vc kick`)
- [ ] 指定ユーザー（1人以上）をVCから即時切断できる
- [ ] 対象ユーザーが同VCにいない場合は ephemeral でエラーを返す
- [ ] `Move Members` 権限がない場合は ephemeral でエラーを返す

### AC-4: タイマー切断 (`/vc kick-timer`)
- [ ] 指定ユーザーを N分後（1-1440）に切断するタイマーを設定できる
- [ ] タイマー発火60秒前に警告メッセージを送信する
- [ ] `/vc cancel` で対象VCのタイマーをキャンセルすると `kick-timer` も合わせてキャンセルされる

### AC-5: VC移動 (`/vc move`, `/vc move-all`)
- [ ] `/vc move @user #channel` で指定ユーザーを指定VCチャンネルへ移動できる
- [ ] `/vc move-all #channel` で現在VCの全人間メンバーを指定VCチャンネルへ移動できる
- [ ] 移動先チャンネルが存在しない or ボイスチャンネルでない場合は ephemeral でエラーを返す

### AC-6: 既存テストが通過し続ける
- [ ] `cd vc-disconnect-bot && uv run pytest tests/` が全テスト通過する
- [ ] 新機能に対応するテストが追加されている

---

## Assumptions Exposed

1. **py-cordは1ギルド複数VoiceClientをサポートする** — 複数VC同時タイマーでボットが各VCに入居する場合に必要。入居不要な設計を選択すれば不問。
2. **`voice_channel.members` はボット不在でも参照可能** — py-cordのキャッシュ依存だが通常はOK。
3. **`/vc kick-timer` のタイマーはギルドレベルで1つ存在するVCタイマーと共存する** — 同一VCに `timer` と `kick-timer` が同時設定される可能性がある（スコープを分けて管理する必要あり）。
4. **`/vc move` に使う `member.move_to(channel)` は `Move Members` 権限で可能** — 切断と同じ権限で動作する想定。

---

## Technical Context

### 現状のアーキテクチャ（トレース済み）
```
_guild_states: dict[int, GuildState]   # guild_id → 1つのGuildState
GuildState: voice_client, voice_channel, task, timer, mode, trigger_time, text_channel
GuildTimer: asyncio.Task で countdown → _disconnect_all
```

### 変更が必要な箇所

**`bot.py`:**
- `_guild_states` の型を `dict[int, dict[str, GuildState]]`（guild_id → channel_id → GuildState）に変更
- `_has_active_timer(guild_id)` → `_has_active_timer(guild_id, channel_id)` に変更
- `_get_or_connect` をVC入居不要な設計に変更（または複数接続対応）
- `on_voice_state_update` に自動キャンセルロジックを追加
- 新コマンド `kick`, `kick-timer`, `move`, `move-all` を追加

**`timer.py`:**
- `GuildTimer._disconnect_all` に対象メンバーリストの絞り込みサポートを追加（`target_members: list[Member] | None`）
- `target_members=None` のときは従来通り全員切断

---

## Ontology

| エンティティ | 定義 |
|---|---|
| `GuildState` | ギルド×VCチャンネルのタイマー状態（変更後は channel_id ごとに存在） |
| `GuildTimer` | asyncio ベースのカウントダウン + 切断実行エンジン |
| VC タイマー | `/vc timer` or `/vc alarm` で設定されるチャンネル全員向けタイマー |
| キックタイマー | `/vc kick-timer` で設定される特定ユーザー向けタイマー |
| 対象メンバー | 切断/移動の対象となる人間メンバー（@メンションで指定） |

---

## Interview Transcript

| Round | 質問 | 回答 |
|---|---|---|
| 1 | 欲しい機能を選択 | 複数VC同時対応、空チャンネル自動停止、特定の人物のみ切断（即時+タイマー）、移動機能（特定人物+全員） |
| 2 | 「移動機能」はどこへの移動か | 別のVCチャンネルへ移動 |
| 3 | 特定人物の選択方法 | @メンションで指定 |
| 4 | 移動機能にタイマーが必要か | 切断だけタイマー対応、移動は即時のみ |
| 5 | 複数VCでボットはVCに入居必要か | どちらでもよい |
| 6 | 除外する機能（Non-goals） | 特になし（全て実装対象として扱う） |
| 7 | 複数VCのコマンド設計 | 同じ/vc timerを別VCで呼び出す形式でよい |
| 8 | 新コマンド名の確認 | /vc kick, /vc kick-timer, /vc move, /vc move-all の案通りでよい |

---

## Trace Findings

**Most likely explanation (from trace):** vc-disconnect-botはJapanese single-server MVPとして正常動作するが、3レーン全てが同一問題を収束発見: `on_voice_state_update` が空チャンネルでタイマーをキャンセルしない。

**Key trace discoveries shaping this spec:**
1. **デッドtimezone config** (`timer.py:11`, `config.yaml:2`) — `timezone`キーが実行時に参照されていない（今回のスコープ外だが既知の技術負債）
2. **`_guild_states` の単一タイマー制限** — 3箇所のガード (`bot.py:98-104`, `148-153`, `190-195`) を全て改修する必要がある
3. **`perms.connect` のみ事前チェック** — `move_members` 権限チェックをコマンド起動時に追加すべき（新コマンドの実装で同時対処）
4. **`GuildTimer` はコンストラクタインジェクション設計** — `target_members` パラメータを追加するだけで特定ユーザー対応が可能
