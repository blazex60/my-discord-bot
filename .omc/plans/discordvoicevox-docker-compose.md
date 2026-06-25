# DiscordVoiceVox Docker Compose 完全統合プラン

**ステータス:** pending approval  
**作成日:** 2026-06-10

---

## 要件サマリー

現在の `docker-compose.yml` はボット本体のみで、VOICEVOX Engine・Lavalink・PostgreSQL はホスト側で別途起動する前提（`network_mode: host`）。  
これを **完全自己完結型の Docker Compose スタック** に統合する。GTX 970（CUDA 12.x）による GPU 加速も活用する。

---

## 受け入れ基準

- [ ] `docker compose up -d` 一発でスタック全体が起動する
- [ ] VOICEVOX Engine がコンテナ内で GPU を使って音声合成できる（`nvidia-smi` で GPU 確認可能）
- [ ] Lavalink がコンテナ内で起動し、ボットから接続できる
- [ ] PostgreSQL がコンテナ内で起動し、データがボリュームに永続化される
- [ ] ボット全インスタンスがサービス名（`voicevox-engine`, `lavalink`, `postgres`）でそれぞれのサービスに到達できる
- [ ] `docker compose down` 後も PostgreSQL のデータが失われない
- [ ] 既存の `user_dict`, `guild_setting`, `cache`, `logs` ボリュームが正常にマウントされる

---

## リスクと軽減策

| リスク | 内容 | 軽減策 |
|---|---|---|
| GTX 980 Ti (CC 5.2) 非対応 | ONNX Runtime の CUDA EP は CC 6.0+ 必須の場合がある | CPU フォールバック用に `IS_GPU=False` の env コメントを残す。起動後 `docker logs dvvox-engine` で確認 |
| NVIDIA Container Toolkit 未インストール | GPU パススルーには host 側に `nvidia-container-toolkit` が必要 | 事前確認手順を検証ステップに記載 |
| Lavalink パスワード不一致 | application.yml とボット設定のパスワードが一致しないと接続失敗 | `.env` で一元管理、ボット env ファイルから参照 |
| 既存データの移行 | 現在ホスト上にある `guild_setting`, `user_dict` 等をボリュームに移行が必要 | Named volume ではなく bind mount を使い、既存パスをそのまま活用できるよう設計 |

---

## 実装ステップ

### Step 1: 前提確認（手動）

```bash
# NVIDIA Container Toolkit の確認
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi
```

上記が通らない場合は以下でインストール:
```bash
# Arch Linux
sudo pacman -S nvidia-container-toolkit
sudo systemctl restart docker
```

---

### Step 2: `lavalink/application.yml` 新規作成

**ファイル:** `DiscordVoiceVox/lavalink/application.yml`

```yaml
server:
  port: 2333
  address: 0.0.0.0

lavalink:
  plugins:
    - dependency: "dev.lavalink.youtube:youtube-plugin:1.11.2"
      snapshot: false
  server:
    password: "${LAVALINK_PASSWORD:-youshallnotpass}"
    sources:
      youtube: false   # youtube-plugin を使用するため無効化
      bandcamp: true
      soundcloud: true
      twitch: true
      vimeo: true
      http: true
      local: false
    filters:
      volume: true
      equalizer: true
      karaoke: true
      timescale: true
      tremolo: true
      vibrato: true
      distortion: true
      rotation: true
      channelMix: true
      lowPass: true

plugins:
  youtube:
    enabled: true
    allowSearch: true
    allowDirectVideoIds: true
    allowDirectPlaylistIds: true
    clients:
      - MUSIC
      - ANDROID_TESTSUITE
      - TV_EMBEDDED
      - TVHTML5EMBEDDED

logging:
  level:
    root: INFO
    lavalink: INFO
```

---

### Step 3: `.env`（プロジェクトルート）新規作成

**ファイル:** `DiscordVoiceVox/.env`

docker-compose.yml から参照するシークレット共通定義:

```dotenv
# Compose スタック共通シークレット
POSTGRES_PASSWORD=change_me_strong_password
LAVALINK_PASSWORD=change_me_lavalink_password
```

---

### Step 4: `env/bot.env.example` 更新

`network_mode: host` 廃止にともないホスト名を変更:

```diff
-DB_HOST=127.0.0.1
+DB_HOST=postgres

-VOICEVOX_HOST=127.0.0.1:50021
-VOICEVOX_HOSTS=127.0.0.1:50021
-VOICEVOX_QUERY_HOST=127.0.0.1:50021
+VOICEVOX_HOST=voicevox-engine:50021
+VOICEVOX_HOSTS=voicevox-engine:50021
+VOICEVOX_QUERY_HOST=voicevox-engine:50021

-LAVALINK_HOST=127.0.0.1:2333
+LAVALINK_HOST=lavalink:2333

+LAVALINK_PASSWORD=change_me_lavalink_password
```

---

### Step 5: `docker-compose.yml` 完全書き換え

`network_mode: host` を廃止し、カスタムブリッジネットワーク `voicevox-net` に全サービスを配置:

```yaml
name: discordvoicevox

networks:
  voicevox-net:
    driver: bridge

volumes:
  postgres-data:

services:
  # ============================================================
  # Infrastructure
  # ============================================================
  postgres:
    image: postgres:16-alpine
    container_name: dvvox-postgres
    restart: unless-stopped
    networks: [voicevox-net]
    environment:
      POSTGRES_DB: postgres
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  voicevox-engine:
    image: voicevox/voicevox_engine:nvidia-ubuntu22.04-latest
    container_name: dvvox-engine
    restart: unless-stopped
    networks: [voicevox-net]
    # GPU パススルー（NVIDIA Container Toolkit 必須）
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:50021/version || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 90s  # モデルロードに時間がかかるため長めに設定

  lavalink:
    image: ghcr.io/lavalink-devs/lavalink:4
    container_name: dvvox-lavalink
    restart: unless-stopped
    networks: [voicevox-net]
    environment:
      LAVALINK_PASSWORD: ${LAVALINK_PASSWORD:-youshallnotpass}
    volumes:
      - ./lavalink/application.yml:/opt/Lavalink/application.yml:ro
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:2333/version || exit 1"]
      interval: 20s
      timeout: 10s
      retries: 5
      start_period: 30s

  # ============================================================
  # Bot instances（depends_on で起動順序を保証）
  # ============================================================
  voicevox-main:
    build: .
    container_name: voicevox-main
    restart: unless-stopped
    networks: [voicevox-net]
    env_file: env/bot-main.env
    depends_on:
      postgres:        {condition: service_healthy}
      voicevox-engine: {condition: service_healthy}
      lavalink:        {condition: service_healthy}
    volumes:
      - /root/DiscordVoiceVox/user_dict:/app/user_dict
      - /root/DiscordVoiceVox/logs:/app/logs
      - /root/DiscordVoiceVox/guild_setting:/app/guild_setting
      - /root/DiscordVoiceVox/cache:/app/cache

  voicevox-c:
    build: .
    container_name: voicevox-c
    restart: unless-stopped
    networks: [voicevox-net]
    env_file: env/bot-c.env
    depends_on:
      postgres:        {condition: service_healthy}
      voicevox-engine: {condition: service_healthy}
      lavalink:        {condition: service_healthy}
    volumes:
      - /home/len/DiscordVoiceVox-c/user_dict:/app/user_dict
      - /home/len/DiscordVoiceVox-c/logs:/app/logs
      - /home/len/DiscordVoiceVox-c/guild_setting:/app/guild_setting
      - /home/len/DiscordVoiceVox-c/cache:/app/cache

  voicevox-d:
    build: .
    container_name: voicevox-d
    restart: unless-stopped
    networks: [voicevox-net]
    env_file: env/bot-d.env
    depends_on:
      postgres:        {condition: service_healthy}
      voicevox-engine: {condition: service_healthy}
      lavalink:        {condition: service_healthy}
    volumes:
      - /home/len/DiscordVoiceVox-d/user_dict:/app/user_dict
      - /home/len/DiscordVoiceVox-d/logs:/app/logs
      - /home/len/DiscordVoiceVox-d/guild_setting:/app/guild_setting
      - /home/len/DiscordVoiceVox-d/cache:/app/cache

  voicevox-e:
    build: .
    container_name: voicevox-e
    restart: unless-stopped
    networks: [voicevox-net]
    env_file: env/bot-e.env
    depends_on:
      postgres:        {condition: service_healthy}
      voicevox-engine: {condition: service_healthy}
      lavalink:        {condition: service_healthy}
    volumes:
      - /home/len/DiscordVoiceVox-e/user_dict:/app/user_dict
      - /home/len/DiscordVoiceVox-e/logs:/app/logs
      - /home/len/DiscordVoiceVox-e/guild_setting:/app/guild_setting
      - /home/len/DiscordVoiceVox-e/cache:/app/cache

  voicevox-z:
    build: .
    container_name: voicevox-z
    restart: unless-stopped
    networks: [voicevox-net]
    env_file: env/bot-z.env
    depends_on:
      postgres:        {condition: service_healthy}
      voicevox-engine: {condition: service_healthy}
      lavalink:        {condition: service_healthy}
    volumes:
      - /home/len/DiscordVoiceVox-z/user_dict:/app/user_dict
      - /home/len/DiscordVoiceVox-z/logs:/app/logs
      - /home/len/DiscordVoiceVox-z/guild_setting:/app/guild_setting
      - /home/len/DiscordVoiceVox-z/cache:/app/cache

  voicevox-h:
    build: .
    container_name: voicevox-h
    restart: unless-stopped
    networks: [voicevox-net]
    env_file: env/bot-h.env
    depends_on:
      postgres:        {condition: service_healthy}
      voicevox-engine: {condition: service_healthy}
      lavalink:        {condition: service_healthy}
    volumes:
      - /home/len/DiscordVoiceVox-h/user_dict:/app/user_dict
      - /home/len/DiscordVoiceVox-h/logs:/app/logs
      - /home/len/DiscordVoiceVox-h/guild_setting:/app/guild_setting
      - /home/len/DiscordVoiceVox-h/cache:/app/cache
```

---

### Step 6: 各 `env/bot-*.env` の更新

既存の各インスタンス env ファイルを以下のように更新（Step 4 の diff を適用）:

```bash
# 例: bot-main.env の更新
sed -i \
  -e 's/DB_HOST=127.0.0.1/DB_HOST=postgres/' \
  -e 's|VOICEVOX_HOST=127.0.0.1:50021|VOICEVOX_HOST=voicevox-engine:50021|' \
  -e 's|VOICEVOX_HOSTS=127.0.0.1:50021|VOICEVOX_HOSTS=voicevox-engine:50021|' \
  -e 's|VOICEVOX_QUERY_HOST=.*|VOICEVOX_QUERY_HOST=voicevox-engine:50021|' \
  -e 's|LAVALINK_HOST=127.0.0.1:2333|LAVALINK_HOST=lavalink:2333|' \
  env/bot-main.env
```

---

## 検証ステップ

```bash
# 1. GPU 前提確認
docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi

# 2. スタック起動
cd DiscordVoiceVox
docker compose up -d

# 3. 各サービスの起動確認
docker compose ps

# 4. VOICEVOX GPU 確認（ログで GPU デバイス使用を確認）
docker logs dvvox-engine 2>&1 | grep -E "gpu|cuda|device|GPU"

# 5. VOICEVOX API 疎通確認
curl http://localhost:50021/version  # ports マッピング不要。コンテナ内から voicevox-engine:50021 で到達

# 6. Lavalink ヘルスチェック
docker compose exec dvvox-lavalink wget -qO- http://localhost:2333/version

# 7. PostgreSQL 接続確認
docker compose exec dvvox-postgres psql -U postgres -c "\l"

# 8. ボットログ確認
docker compose logs voicevox-main --tail=50
```

---

## GTX 980 Ti GPU 非対応時のフォールバック手順

VOICEVOX Engine が GPU 初期化に失敗する場合（CC 5.2 が ONNX Runtime 対象外の場合）:

```yaml
# docker-compose.yml の voicevox-engine を以下に変更
voicevox-engine:
  image: voicevox/voicevox_engine:cpu-ubuntu22.04-latest
  # deploy セクション（GPU設定）を削除
```

---

## 変更ファイル一覧

| ファイル | 操作 |
|---|---|
| `docker-compose.yml` | 完全書き換え |
| `env/bot.env.example` | ホスト名を更新 |
| `env/bot-*.env`（既存の各インスタンス設定） | ホスト名を更新 |
| `lavalink/application.yml` | 新規作成 |
| `.env` | 新規作成（シークレット定義） |
| `.gitignore` | `.env` の除外確認 |
