"""
Download pre-converted OpenVINO Phi-3.5-mini model for Intel NPU inference.
Run once before starting server.py.
"""

import sys
import os
from pathlib import Path

try:
    from huggingface_hub import snapshot_download
except ImportError:
    print("ERROR: huggingface-hub not installed. Run: pip install huggingface-hub")
    sys.exit(1)

MODEL_REPO = "OpenVINO/Phi-3.5-mini-instruct-int4-ov"
MODEL_DIR = Path(__file__).parent / "model"

print(f"Downloading {MODEL_REPO} to {MODEL_DIR} ...")
print("This is ~2.3 GB — will take a few minutes on a good connection.\n")

snapshot_download(
    repo_id=MODEL_REPO,
    local_dir=str(MODEL_DIR),
    ignore_patterns=["*.msgpack", "*.h5", "flax_*", "tf_*", "rust_*"],
)

print(f"\nModel downloaded to: {MODEL_DIR}")
print("You can now run: python server.py")
