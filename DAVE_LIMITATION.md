# Discord DAVE プロトコルによる制限

## 現状

**Discord Bot経由での音声録音は現在動作しません。**

Discord が導入した **DAVE (Discord Audio & Video Encryption)** エンドツーエンド暗号化プロトコルにより、
py-cord（および他のDiscord Bot ライブラリ）での音声受信機能が完全に壊れています。

## エラーメッセージ

```
RuntimeWarning: Voice reception is currently broken due to Discord's DAVE 
(End-to-End Encryption) protocol.
```

## 追跡情報

- **Issue**: https://github.com/Pycord-Development/pycord/issues/3139
- **Status**: 進行中（py-cord開発チームが対応中）
- **影響**: すべての音声受信機能（WaveSink、録音、等）

## 技術的背景

1. Discordは2024年後半にDAVEプロトコルを導入
2. DAVEはエンドツーエンド暗号化を提供するため、サーバー（Bot）側での復号化が不可能
3. py-cordチームがDAVEプロトコルの実装を進めているが、完了時期は未定

## 一時的な解決策

**現時点では根本的な解決策はありません。**

以下のオプションを検討できます：

### オプション1: py-cordのDAVE対応を待つ
- Issue #3139 を監視
- 対応が完了次第、依存関係を更新

### オプション2: 代替録音方法を使用
- OBS等の外部ツールでDiscord音声をキャプチャ
- ユーザー側でローカル録音してアップロード

### オプション3: 別のプラットフォームを検討
- Discord以外のVCプラットフォーム（Zoom、Google Meet等）で録音
- それらのAPIを使用

## コードの状態

このリポジトリのコードは**技術的には正しく実装されています**：

✅ py-cord dev版 (2.8.0rc2) に対応
✅ カスタムWaveSink実装
✅ WebSocket安定化
✅ エラーハンドリング強化
✅ 暗号化モード対応

しかし、Discord側のプロトコル制限により、音声データの受信自体ができません。

## 推奨アクション

1. **短期**: DAVEサポートの進捗を監視
2. **中期**: 代替録音方法の検討
3. **長期**: py-cordがDAVEに対応したら、即座に対応

## 更新日

2026-04-02
