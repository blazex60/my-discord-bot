"""utils/memory.py のユニットテスト"""

from utils.memory import unload_model


class TestUnloadModel:
    def test_unload_dict(self):
        """ダミーオブジェクトをアンロードできること（例外が発生しないこと）"""
        dummy = {"model": "test"}
        unload_model(dummy)

    def test_unload_list(self):
        """リストオブジェクトをアンロードできること"""
        dummy = [1, 2, 3]
        unload_model(dummy)
