"""モデルアンロード・メモリ解放ユーティリティ"""

import gc


def unload_model(model) -> None:
    """モデルを安全にアンロードして VRAM と RAM を解放する"""
    del model
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
