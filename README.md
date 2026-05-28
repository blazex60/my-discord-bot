# my-Discord-bots

個人用 Discord Bot のモノレポ。各ボットは独立したサブディレクトリで管理する。

## ボット一覧

| ディレクトリ | 概要 |
|---|---|
| [`discord-minutes-bot/`](discord-minutes-bot/README.md) | Discord VC 録音 → オフライン ASR/LLM → 議事録自動生成 |
| [`chat-summary-bot/`](chat-summary-bot/README.md) | 雑談チャンネルの要約・話題検索・追いつきサポート |
| [`vc-disconnect-bot/`](vc-disconnect-bot/README.md) | タイマー・アラームで VC の全員または特定ユーザーを切断・移動 |

## 共通環境

| 項目 | 内容 |
|---|---|
| OS | Linux (Arch Linux / Ubuntu 22.04 LTS) |
| GPU | NVIDIA GTX 980 Ti (VRAM 6GB) / CUDA 12.x |
| RAM | 32GB |
| Python | 3.12（各ボットで uv 管理） |

## 共通ルール

- シークレット（`DISCORD_TOKEN` 等）は各ボットの `.env` に記載し、ソースコードには絶対に書かない
- 外部 AI API（OpenAI API・Anthropic API 等）は使用しない。すべてローカル LLM で処理する
- 各ボットのセットアップ・使い方は各ディレクトリの `README.md` を参照

## ライセンス

MIT
