# Open Questions

## musicbot-webui-playlist-login-plan - 2026-07-14
- [ ] Web UI にギルド切り替えUIが必要か（単一ギルド前提か） — spec line 92 で未確認。マルチギルド運用時の import/control 先の指定方法に影響
- [ ] 具体的な `WEB_PORT` / `BOT_API_PORT` の値と Cloudflare Tunnel のホスト名 — 各OAuthプロバイダのコンソールに登録する redirect URI を確定するために必要
- [ ] 暗号化鍵のローテーション運用手順（バックアップ保持者・ローテーション頻度） — pre-mortem #3。鍵紛失時に全トークンが復号不能になるため運用ルールが必要
- [ ] YouTube Data API のクォータ予算 — 非公開プレイリスト一覧取得のAPI消費量と上限到達時のUX
