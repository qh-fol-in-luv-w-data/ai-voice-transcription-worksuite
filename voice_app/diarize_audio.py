#!/usr/bin/env python3
"""
Run pyannote speaker diarization in a fresh subprocess.
Usage: python diarize_audio.py <wav_path> <hf_token> [min_speakers] [max_speakers]
Output: JSON array of {"start": float, "end": float, "speaker": str}
"""
import os
os.environ["USE_NNPACK"] = "0"
os.environ["DNNL_PRIMITIVE_CACHE_CAPACITY"] = "0"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

import sys
import json

# Add voice_app dir to path so _torchaudio_compat can be found
sys.path.insert(0, os.path.dirname(__file__))


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Missing arguments: wav_path and hf_token required"}), file=sys.stderr)
        sys.exit(1)

    wav_path   = sys.argv[1]
    hf_token   = sys.argv[2] if sys.argv[2] else None
    min_spk    = int(sys.argv[3]) if len(sys.argv) > 3 else None
    max_spk    = int(sys.argv[4]) if len(sys.argv) > 4 else None

    print("DEBUG: Importing torch...", flush=True)
    import torch
    print("DEBUG: torch imported", flush=True)

    if hasattr(torch.backends, "nnpack"):
        torch.backends.nnpack.enabled = False
    if hasattr(torch.backends, "mkldnn"):
        torch.backends.mkldnn.enabled = False
    torch.set_num_threads(1)

    if hf_token:
        os.environ["HUGGING_FACE_HUB_TOKEN"] = hf_token
        os.environ["HF_TOKEN"] = hf_token

    print("DEBUG: Applying torchaudio compat shims...", flush=True)
    import _torchaudio_compat  # noqa: F401 — patches torchaudio + huggingface_hub

    print("DEBUG: Loading diarization pipeline...", flush=True)
    from pyannote.audio import Pipeline
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")

    print("DEBUG: Pipeline loaded, running diarization...", flush=True)

    kwargs = {}
    if min_spk is not None:
        kwargs["min_speakers"] = min_spk
    if max_spk is not None:
        kwargs["max_speakers"] = max_spk

    diarization = pipeline(wav_path, **kwargs)

    segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append({
            "start":   round(turn.start, 3),
            "end":     round(turn.end,   3),
            "speaker": speaker,
        })

    print(f"DEBUG: Done — {len(segments)} segments", flush=True)
    print(json.dumps(segments))
    sys.exit(0)


if __name__ == "__main__":
    main()
