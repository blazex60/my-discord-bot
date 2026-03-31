"""設定ファイルのバリデーションテスト"""

from pathlib import Path

import yaml


def test_config_yaml_exists():
    """config.yaml が存在すること"""
    assert (Path(__file__).parent.parent / "config.yaml").exists()


def test_config_required_keys(config):
    """必須キーが揃っていること"""
    assert "discord" in config
    assert "asr" in config
    assert "llm" in config
    assert "storage" in config


def test_config_no_token(config):
    """config.yaml に discord.token キーが含まれていないこと（セキュリティ）"""
    assert "token" not in config.get("discord", {})


def test_asr_models(config):
    """ASR モデル設定が正しいこと"""
    assert config["asr"]["primary_model"] == "whisper-large-v3"
    assert config["asr"]["fallback_model"] == "whisper-medium"
    assert config["asr"]["device"] == "cuda"


def test_llm_ctx_limit(config):
    """n_ctx が 16384 未満であること"""
    assert config["llm"]["n_ctx"] < 16384


def test_chunk_size(config):
    """chunk_size_tokens が 2200 以下であること"""
    assert config["llm"]["chunk_size_tokens"] <= 2200
