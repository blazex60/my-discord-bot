# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## リポジトリ概要

複数の Discord Bot をまとめて管理するモノレポ。
各ボットは独立したサブディレクトリに格納され、それぞれ独自の依存関係・設定・CLAUDE.md を持つ。

---

## 共通環境

| 項目 | 内容 |
|---|---|
| OS | Linux (Arch Linux / Ubuntu 22.04 LTS) |
| GPU | NVIDIA GTX 980 Ti (VRAM 6GB) / CUDA 12.x |
| RAM | 32GB |

---

## ボット一覧

| ディレクトリ | 概要 |
|---|---|
| `discord-minutes-bot/` | Discord VC 録音 → オフラインASR/LLM → 議事録自動生成 |
| `chat-summary-bot/` | 雑談チャンネルのテキスト要約・話題検索・追いつきサポート |

---

## 共通ルール

- 各ボットのディレクトリ内にある `CLAUDE.md` を参照して作業する。
- `DISCORD_TOKEN` などのシークレットは各ボットの `.env` に記載し、ソースコードには絶対に書かない。
- 外部AI API（OpenAI API、Anthropic API 等）は使用しない。
