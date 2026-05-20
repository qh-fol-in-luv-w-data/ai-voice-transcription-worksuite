#!/usr/bin/env python3
"""
Standalone script: Extract speaker embedding in a fresh subprocess.
Bypasses DNNL/NNPACK "could not create a primitive" error caused by Gunicorn --preload + fork.
Usage: python extract_embedding.py <wav_path> <hf_token>
Output: JSON array (embedding vector) written to stdout.
"""
import os
# MUST set before ANY torch/numpy import
os.environ["USE_NNPACK"] = "0"
os.environ["DNNL_PRIMITIVE_CACHE_CAPACITY"] = "0"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import sys
import json
import numpy as np


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Missing arguments: wav_path and hf_token required"}))
        sys.exit(1)

    wav_path = sys.argv[1]
    hf_token = sys.argv[2]

    import torch
    if hasattr(torch.backends, 'nnpack'):
        torch.backends.nnpack.enabled = False
    if hasattr(torch.backends, 'mkldnn'):
        torch.backends.mkldnn.enabled = False
    torch.set_num_threads(1)

    # Patch torch.load for weights_only compatibility
    from functools import partial
    _orig_load = torch.load
    torch.load = partial(_orig_load, weights_only=False)

    from pyannote.audio import Model
    from pyannote.audio.core.inference import Inference

    model = Model.from_pretrained("pyannote/embedding", use_auth_token=hf_token)
    inference = Inference(model, window="whole")
    embedding = inference(wav_path)

    # Output embedding as JSON to stdout
    print(json.dumps(embedding.tolist()))
    sys.exit(0)


if __name__ == "__main__":
    main()
