# Plan: music-bot 曲スキップ・途中再生バグ修正

**Status:** pending approval  
**Date:** 2026-06-26

---

## 症状

ウォッチドッグ追加後、以下の挙動が発生：
1. 曲がトラックの途中（約10秒の位置）から再生される
2. 短時間でキューの次の曲に勝手にスキップされる

---

## 根本原因

### 原因 1（主因）: `-reconnect_at_eof 1` の誤用

**ファイル:** `music-bot/player.py:16-19`

```python
FFMPEG_OPTIONS: dict[str, str] = {
    "before_options": (
        "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -reconnect_at_eof 1"
    ),
    ...
}
```

`-reconnect_at_eof 1` はライブストリーム向けのオプション。VOD（録画済みYouTube動画）に使うと：

- 曲が自然に終了（EOF）→ FFmpegが同じ googlevideo URL に再接続
- 再接続後、ストリームの中間位置（HTTP Range ヘッダーにより）から音声を送信
- ユーザーには「10秒あたりから再生が始まる」ように聞こえる
- やがて再接続URLが無効化またはウォッチドッグが検知 → `_vc.stop()` → キュー進行
- 結果：「途中から再生 → 次の曲にスキップ」

### 原因 2（副因）: ウォッチドッグタスクの蓄積

**ファイル:** `music-bot/player.py:96`

```python
asyncio.create_task(self._watchdog(monitored))  # キャンセルされない
```

`play_next()` を呼ぶたびに新しいウォッチドッグタスクが作成されるが、**前の曲のウォッチドッグをキャンセルする処理がない**。

影響：
- 曲N のウォッチドッグは曲N が終了してもループし続ける
- `is_playing()` = True（次の曲が再生中）のため `break` しない
- 曲N の `source.last_read_at` は曲N終了時点から更新されない
- 30秒後に `stale >= _STALL_TIMEOUT` となり `_vc.stop()` を発火
- 現在再生中の曲（曲N+1）が途中で強制スキップされる

---

## 修正方針

### 修正 1: `-reconnect_at_eof 1` を削除

`player.py:16-19` の `FFMPEG_OPTIONS` から除去するだけ。  
`-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5` は残す（mid-song の回線断対策として有効）。

### 修正 2: ウォッチドッグタスクの追跡とキャンセル

`GuildPlayer` に `_watchdog_task: asyncio.Task | None = None` 属性を追加し、`play_next()` の先頭で前のタスクをキャンセルする。

```python
# play_next() 内、_vc.play() の前に追加
if self._watchdog_task and not self._watchdog_task.done():
    self._watchdog_task.cancel()
...
self._vc.play(monitored, after=_after)
self._watchdog_task = asyncio.create_task(self._watchdog(monitored))
```

---

## 変更対象ファイル

| ファイル | 変更内容 |
|---|---|
| `music-bot/player.py` | `FFMPEG_OPTIONS` から `-reconnect_at_eof 1` を削除；`_watchdog_task` 属性追加とキャンセル処理追加 |

---

## 受け入れ条件

- [ ] 曲が先頭（0:00）から再生される
- [ ] 通常の曲終了でキューが正常に次の曲へ進む
- [ ] 曲の途中で音声がなくなる現象（元の問題）が再発しない
- [ ] ウォッチドッグログ (`Playback stalled`) が通常再生中に出ない
- [ ] `/skip` コマンドが正常動作する
- [ ] ループモード（TRACK / QUEUE）が正常動作する

---

## リスクと軽減策

| リスク | 軽減策 |
|---|---|
| 元の「音が途切れる」問題が再発 | `-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5` は保持。ウォッチドッグも引き続き機能 |
| タスクキャンセルによる副作用 | `asyncio.Task.cancel()` は CancelledError を送出するが、ウォッチドッグの `while` ループは `asyncio.sleep` 中のキャンセルを安全に処理できる |

---

## 検証手順

1. ボットを起動しVCに参加
2. 複数曲をキューに追加して再生
3. 各曲が 0:00 から始まることを確認
4. 自然に次の曲へ移行することを確認
5. ログに意図しない `Playback stalled` が出ないことを確認
6. `/skip` で明示的にスキップし、正常動作を確認
