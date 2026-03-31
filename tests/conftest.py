"""pytest 共通フィクスチャ"""

from pathlib import Path

import pytest
import yaml


@pytest.fixture
def config():
    """config.yaml を読み込んで返す"""
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def tmp_recordings_dir(tmp_path):
    """一時録音ディレクトリ"""
    recordings = tmp_path / "recordings"
    recordings.mkdir()
    return recordings
