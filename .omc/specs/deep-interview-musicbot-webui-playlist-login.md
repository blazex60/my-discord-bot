# Deep Interview Spec: music-bot Web UI + プレイリスト連携(Spotify/Apple Music/YouTube) + ログイン機能

## Metadata
- Interview ID: musicbot-webui-playlist-login-2026-07-14
- Rounds: 10 (+ Round 0 トポロジー確認 + ソフトチェックポイント)
- Final Ambiguity Score: 約24%
- Type: brownfield
- Generated: 2026-07-14
- Threshold: 0.2
- Threshold Source: default
- Initial Context Summarized: no
- Status: BELOW_THRESHOLD_EARLY_EXIT(ユーザーが現状の明確さでの進行を明示的に選択)

## Clarity Breakdown
| 次元 | スコア | 重み | 加重 |
|------|--------|------|------|
| Goal Clarity | 0.85 | 0.35 | 0.298 |
| Constraint Clarity | 0.85 | 0.25 | 0.213 |
| Success Criteria | 0.70 | 0.25 | 0.175 |
| Context Clarity | 0.50 | 0.15 | 0.075 |
| **Total Clarity** | | | **0.761** |
| **Ambiguity** | | | **23.9%** |

残存ギャップはほぼ Context Clarity(Bot⇔Webサーバー間のIPC方式などの実装詳細)に集中しており、これは omc-plan の Architect レビュー段階で解決すべき技術選定であるとユーザーが判断し、早期終了を選択した。

## Topology
| コンポーネント | 状態 | 説明 | カバレッジ / 後回し理由 |
|--------------|------|------|--------------------------|
| Web UI | active | ボット操作・キュー閲覧のダッシュボード | 総合ダッシュボード(再生コントロール+キュー操作+プレイリスト参照・取り込みを同一画面)。別プロセス/別コンテナで稼働 |
| プレイリスト連携 | active | Spotify/Apple Music/YouTubeのプレイリストをインポートしキューに投入 | Spotify+YouTube(Google OAuth)を先行実装。Apple Musicは有料Developer Program契約が必須なため後回し。ワンショット取り込みのみ(継続同期なし) |
| ログイン/認証 | active | Web UIおよび外部サービスへの認証機構 | Discordログイン(WebUIアクセス制御)+各サービスへの個別OAuth連携の両方 |

## Goal
既存の music-bot(discord.js v14, brownfield)に、以下を追加する:

1. **Web UI**: 現在プレイリスト/キュー操作用の一部依存(fastify, react-router-dom, better-sqlite3)のみ存在し未実装のダッシュボードを構築する。再生コントロール、キューの閲覧・操作、外部プレイリストの参照とDiscordキューへの取り込みを単一画面で行う総合ダッシュボードとする。
2. **プレイリスト連携**: Spotify・YouTube(Google OAuth経由)のプレイリストをWeb UI上でユーザーが選択し、その場でDiscordキューにワンショットで一括投入する。Apple Musicは有料Developer Program契約が必要なため初回スコープ外(後回し)。
3. **ログイン/認証**: Discordアカウントによるログインで Web UI へのアクセスを制御しつつ、ログイン後にユーザーが個別にSpotify/YouTubeアカウントをOAuth連携できるようにする。

## Constraints
- Web UI の操作権限: Bot と同じボイスチャンネルに参加しているユーザーは基本操作(再生コントロール・キュー編集)が可能。Admin ロールを持つユーザーは VC 在室に関わらず無条件で拡張操作が可能な権限階層とする。
- Web UI の公開範囲: Cloudflare Tunnel + 自前ドメインで外部(スマホ・外出先含む)からもアクセス可能にする。アクセス制御はネットワーク位置ではなく上記の権限モデル(VC在室/Admin)に基づく。
- Web サーバー(fastify)は既存の Discord Bot プロセスとは**別プロセス/別コンテナ**として分離する(docker-compose に新規サービスとして追加)。Bot プロセスとの連携方式(IPC/API)は実装フェーズ(Architect レビュー)で確定する。
- プレイリスト連携は**ワンショット取り込みのみ**。取り込み後の元プレイリスト側の変更を追従する継続同期機能は実装しない。
- サービス別実装優先度: Spotify(無料Developer App登録)と YouTube(Google OAuth + YouTube Data API、非公開プレイリスト一覧のため既存 yt-dlp 経由の実装とは別途必要)を先行実装。Apple Music(MusicKit JS + 有料 Apple Developer Program + JWS署名鍵)は後回し。
- 認証セッション: Discord ログインセッションは長期間有効(cookieベース)。Spotify/Google の OAuth アクセストークンはリフレッシュトークンで自動更新し、失効時は Web UI 上に「再連携」ボタンを表示する。
- OAuth トークン(access/refresh token)は better-sqlite3 に保存する際、アプリケーションレベルで暗号化する(既存の「DISCORD_TOKEN は .env のみ」方針と一貫した機密情報の取り扱い)。
- DISCORD_TOKEN などの既存シークレット管理方針(.env のみ、ソースコード非記載)を新規追加のシークレット(Spotify Client Secret, Google Client Secret, 暗号化鍵等)にも適用する。

## Non-Goals
- Apple Music 連携(初回リリースでは対象外。将来フェーズとして保留)
- プレイリストの継続的な自動同期(ワンショット取り込みのみ)
- マッチング精度向上のための事前候補選択UI(自動マッチ優先。精度確認は取り込み後の個別編集で対応)

## Acceptance Criteria
- [ ] Discord OAuth でログインすると Web UI にアクセスできる。未ログイン状態ではダッシュボードの機能が利用できない
- [ ] Bot と同じ VC に参加しているユーザーは Web UI から再生コントロール(再生/一時停止/スキップ/音量等)とキュー操作(追加・削除・並べ替え)ができる
- [ ] Admin ロールを持つユーザーは VC に参加していなくても上記の拡張操作ができる
- [ ] ログイン後、ユーザーは Web UI から Spotify アカウントを OAuth 連携できる
- [ ] ログイン後、ユーザーは Web UI から YouTube(Google)アカウントを OAuth 連携できる
- [ ] 連携済みの Spotify/YouTube アカウントの自分のプレイリスト一覧が Web UI に表示される
- [ ] プレイリストを選択すると、各曲が(Spotifyの場合は曲名+アーティスト名でYouTube検索した代替音源として)自動マッチングされ、確度に関わらずワンショットで Discord のキューに一括投入される
- [ ] 取り込み後、各曲のマッチング結果を Web UI 上で確認し、誤りがあれば再検索・差し替えができる
- [ ] Spotify/Google の OAuth トークンが失効した場合、Web UI に「再連携」ボタンが表示され、再認可で復旧できる
- [ ] Spotify/Google の OAuth トークンは better-sqlite3 に暗号化された状態で保存される
- [ ] Web サーバーは既存 Bot プロセスとは別プロセス/別コンテナとして docker-compose 上で起動する
- [ ] Web UI は Cloudflare Tunnel 経由で外部(スマホ含む)からアクセスできる
- [ ] Apple Music 連携ボタン/導線は今回のリリースには含まれない、または明示的に「準備中」等の表示に留める

## Assumptions Exposed & Resolved
| 前提/仮定 | 問いかけ方 | 決定内容 |
|------------|-----------|------------|
| ログインは何のためか(WebUIアクセス制御 or 外部サービス連携) | (A)(B)(C)の選択肢で提示 | 両方: Discordログインでアクセス制御 + 各サービスへの個別OAuth連携 |
| Web UI は誰でも使えて良いのでは(スラッシュコマンドと同じ権限で十分では) | Contrarian: 現行のスラッシュコマンドは誰でも実行可能、と対比して問いかけ | VC在室ユーザーの基本操作 + Admin無条件の拡張操作、という権限階層が必要と判明 |
| Web UI はLAN内限定で十分では(シンプルな構成) | Simplifier: インフラの複雑さを最小化する方向で問いかけ | Cloudflare Tunnel + 自前ドメインで外部公開したいという明確な要望があった |
| プレイリスト連携は同期(継続的追従)が必要では | 動作方式を直接確認 | ワンショット取り込みのみで十分、継続同期は不要と判明 |
| Spotify/Apple/YouTube を同時に全部実装すべきでは | 実装コストの差(Apple Musicの有料契約要件)を提示して優先度を確認 | Spotify+YouTube先行、Apple Musicは後回し |
| 自動マッチングは高精度でないと使い物にならないのでは | マッチング失敗時の振る舞いを確認 | 確度に関わらず自動採用、後から個別編集できれば十分 |
| 新Webサーバーは既存Botプロセスに同居させるのが自然では(実装がシンプル) | アーキテクチャ選択肢を提示(同一プロセス vs 別プロセス) | ユーザーは明示的に別プロセス/別コンテナへの分離を選択 |

## Technical Context (brownfield)
- **既存スタック**: discord.js v14.16 + @discordjs/voice、Node.js >= 20 (ESM)。`src/index.js`, `sessions.js`, `player.js`, `queue.js`, `search.js`, `views.js`, `settings.js`, `permissions.js`, `queueEditorInteractions.js`, `queueEditorView.js`
- **既存の未使用スキャフォールド**: `package.json` に `fastify@5.6.2`, `@fastify/cookie@11.0.2`, `@fastify/static@8.3.0`, `react-router-dom`, `better-sqlite3@12.4.1` が依存関係として存在するが、サーバー起動コード・`src/db/` 実装・実際のルーティングは一切存在しない。`web/` は React 19 + Vite の QA スモークテスト画面(`web/src/main.jsx`, `p0-smoke.jsx`)のみ
- **既存の権限パターン**: `queueEditorInteractions.js` に「Bot と同じ VC にいるユーザーのみ操作可」という権限チェックの前例あり(`interaction.member.voice.channelId === session.connection.joinConfig.channelId`)。Web UI の権限モデルもこのパターンを踏襲する想定
- **既存のプレイリスト機構**: `src/search.js` に `isPlaylistUrl`, `resolveFlatPlaylist`, `PLAYLIST_LIMIT` があり、YouTube の公開プレイリストURLをyt-dlp経由で一括投入する機能は既にある。ただし「ユーザー自身の非公開プレイリスト一覧をログインして閲覧する」には別途 YouTube Data API + Google OAuth の実装が必要(既存のyt-dlp機構とは独立した新規実装)
- **既存の永続化層**: `src/settings.js`(JSONファイルベース、ギルドごとの normalize 設定のみ)。`data/` ディレクトリは現状空。OAuthトークンやサービス連携情報は `better-sqlite3` を新規に活用する想定
- **既存のシークレット管理方針**: `DISCORD_TOKEN` は `.env` のみ、ソースコード非記載。新規追加する `SPOTIFY_CLIENT_SECRET`, `GOOGLE_CLIENT_SECRET`, トークン暗号化鍵等も同方針を踏襲
- **未解決の実装詳細(Architectレビューで確定すべき事項)**:
  - Bot プロセスと Web サーバープロセス間の具体的な連携方式(REST API / 共有SQLite / メッセージキュー等のIPC選定)
  - better-sqlite3 のスキーマ設計(ユーザー・サービス連携・トークン・インポート履歴等のテーブル構成)
  - Discord OAuth のスコープ設計、Cloudflare Tunnel と OAuth リダイレクトURIの具体的な設定
  - マルチギルド運用時の Web UI 上でのギルド切り替えUIの要否(今回のインタビューでは未確認)

## Ontology (Key Entities)
| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| DiscordUser | core domain | discordId, username, role(Admin/Member) | WebUISession を持つ、複数の ServiceLink を持つ |
| Guild | core domain | guildId, name | Bot が参加する、QueueSession を持つ |
| WebUISession | supporting | sessionId, discordUserId, cookie, expiresAt | DiscordUser に紐づく |
| ServiceLink | core domain | id, discordUserId, service(spotify/youtube/apple), accessToken(暗号化), refreshToken(暗号化), expiresAt | DiscordUser に紐づく、Playlist を参照する |
| ExternalPlaylist | core domain | id, service, name, trackCount | ServiceLink 経由で取得、複数の ExternalTrack を持つ |
| ExternalTrack | supporting | title, artist, sourceUrl | ExternalPlaylist に属する、マッチング後 QueueTrack に変換 |
| ImportJob | supporting | id, playlistId, status(進行中/完了/一部失敗), matchedCount, failedCount | ExternalPlaylist から QueueTrack 群を生成する処理単位 |
| QueueTrack | core domain(既存) | title, webpageUrl, streamUrl, duration, requestedBy | GuildQueue に属する(既存 `queue.js` の Track を拡張) |
| Permission | supporting | scope(VC在室/Admin) | DiscordUser の操作可否を決定 |

## Ontology Convergence
| Round | Entity Count | New | Changed | Stable | Stability Ratio |
|-------|-------------|-----|---------|--------|----------------|
| 1 | 2 (DiscordUser, WebUISession) | 2 | - | - | - |
| 3-4 | 4 (+ ServiceLink, ExternalPlaylist) | 2 | - | 2 | 100% |
| 5 | 5 (+ Permission) | 1 | - | 4 | 80% |
| 7 | 7 (+ ExternalTrack, ImportJob) | 2 | - | 5 | 71% |
| 10(最終) | 9 (+ Guild, QueueTrack を明示化) | 2 | - | 7 | 78% |

コアエンティティ(DiscordUser, ServiceLink, ExternalPlaylist, Permission)は Round 5 以降大きな変化なく安定。Round 7-10 での追加は既存概念の具体化(ImportJob, QueueTrack)であり、根本的なオントロジーの揺れではない。

## Interview Transcript
<details>
<summary>Full Q&A (Round 0 + 10 rounds + チェックポイント)</summary>

### Round 0(トポロジー確認)
**Q:** Web UI / プレイリスト連携 / ログイン認証 の3コンポーネントで合っているか
**A:** この3分割で正しい

### Round 1
**Q:** ログイン機能は主に何のためか(WebUIアクセス制限 / 外部サービスOAuth連携 / 両方)
**A:** 両方(Discordログイン + 各サービス連携)
**Ambiguity:** 88.5%

### Round 2
**Q:** Web UIで具体的に何をしたいか
**A:** 総合ダッシュボード(再生コントロール+キュー操作+外部プレイリスト参照・取り込み)
**Ambiguity:** 約77%

### Round 3
**Q:** プレイリスト連携は具体的にどう動くべきか(ワンショット取り込み or 継続同期)
**A:** ワンショット取り込みのみ
**Ambiguity:** 約68%

### Round 4
**Q:** 3つの外部サービス連携の実装優先度(Apple Musicの有料契約要件を提示)
**A:** Spotify+YouTube(Google OAuth)を先行、Apple Musicは後回し
**Ambiguity:** 約58%

### Round 5(Contrarian Mode)
**Q:** Web UIも「Discordログインさえすれば誰でも操作可能」で十分か、それとも制限が必要か
**A:** VC内ユーザーのみ基本操作可、Adminは無条件で拡張操作可
**Ambiguity:** 約48%

### Round 6(Simplifier Mode)
**Q:** Web UIはLAN内のみで十分か、外部からのアクセスも必要か
**A:** Cloudflare Tunnel + 自前ドメインで外部公開したい(VCにさえ入っていればどこでも操作可能に)
**Ambiguity:** 約37%

### Round 7
**Q:** Spotify曲のYouTube自動マッチングの精度/失敗時の振る舞い
**A:** 確度によらず自動マッチしてよいが、後からWeb UIで編集(再検索・差し替え)できるようにする
**Ambiguity:** 約27%

### Round 8
**Q:** 認証が正しく動いていると言える基準(セッション有効期限、OAuthトークン失効時の再連携フロー)
**A:** 長期セッション+自動リフレッシュ+失敗時は再連携ボタン
**Ambiguity:** 約22%

### Round 9
**Q:** 新しいWebサーバー(fastify)は既存のDiscord Botプロセスとどう関係すべきか
**A:** 別プロセス/別コンテナに分離
**Ambiguity:** 約20%

### Round 10
**Q:** Spotify/GoogleのOAuthトークンをSQLiteに保存する際のセキュリティ要件
**A:** アプリレベルで暗号化して保存
**Ambiguity:** 約24%(見直し後)

### チェックポイント(Round 10到達によるソフト警告)
**Q:** 現在の曖昧度約24%。インタビューを続けるか、現状で仕様書作成に進むか
**A:** 現在の明確さで仕様書作成に進む

</details>
