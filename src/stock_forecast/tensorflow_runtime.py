from __future__ import annotations

import os


def configure_tensorflow_runtime() -> None:
    """Keep local runs on CPU unless the user explicitly enables GPU."""
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
