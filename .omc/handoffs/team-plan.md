## Handoff: team-plan → team-exec

- **Decided**: `/queue` を GUI 化。UI = StringSelectMenu(曲選択) + 操作ボタン(↑/↓/次に再生/ジャンプ/削除)。状態はステートレス（ページ番号・選択インデックスを custom_id にエンコード）。編集権限は同じVCの全員。表示はパブリック(共有メッセージ)。編集対象は `upcoming()` のみ、現在再生中トラックは対象外。詳細設計・完全なコードスニペットは `.omc/plans/musicbot-queue-gui-editor.md` を参照。
- **Rejected**: Map ベースの `QueueEditorStore`（再起動で状態消失・掃除が必要）。移動先ジャンプをセレクトメニューにする案（2段階選択が複雑）。現在再生中トラックの編集対応。ephemeral(実行者のみ)表示。
- **Risks**: 複数ユーザー同時編集による表示ズレ → 操作直前に selectedIndex/page を再検証。StringSelectMenu は0件オプション不可 → upcoming 0件時は省略描画が必須。
- **Files**: `music-bot/src/queue.js`（既存, 変更）, `music-bot/src/queueEditorView.js`（新規）, `music-bot/src/queueEditorInteractions.js`（新規）, `music-bot/src/index.js`（既存, 変更）, `music-bot/src/commands/queue.js`（既存, 変更）, `music-bot/src/queue.test.js`（新規）, `music-bot/package.json`（既存, 変更: testスクリプト追加）
- **Remaining**: team-exec で上記ファイルを実装。team-verify でユニットテスト実行 + コードレビュー。
