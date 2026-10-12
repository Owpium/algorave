"""Demucs (demucs-torchcodec) stem separation with soundfile I/O.
Avoids torchcodec's AudioEncoder (needs shared FFmpeg DLLs on Windows).
Usage: python sep_stems.py <input_audio> <out_dir> [--model htdemucs] [--device cuda]
"""
import argparse, time
from pathlib import Path
import numpy as np
import soundfile as sf
import torch
import librosa
from demucs.api import Separator

ap = argparse.ArgumentParser()
ap.add_argument("input")
ap.add_argument("out_dir")
ap.add_argument("--model", default="htdemucs")
ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
ap.add_argument("--shifts", type=int, default=1)
a = ap.parse_args()

t0 = time.time()
sep = Separator(model=a.model, device=a.device, shifts=a.shifts, progress=False)
sr = sep.samplerate
# decode with librosa (soundfile for wav/flac, audioread/ffmpeg fallback for mp3)
y, _ = librosa.load(a.input, sr=sr, mono=False)
if y.ndim == 1:
    y = np.stack([y, y])
wav = torch.from_numpy(np.ascontiguousarray(y, dtype=np.float32))
t1 = time.time()
_, stems = sep.separate_tensor(wav, sr)
if a.device.startswith("cuda"):
    torch.cuda.synchronize()
t2 = time.time()
out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
for name, s in stems.items():
    s = s.cpu().numpy().T
    peak = np.abs(s).max()
    if peak > 0.999:
        s = s / (1.01 * peak)
    sf.write(out / f"{name}.wav", s, sr, subtype="PCM_16")
print(f"device={a.device} gpu={torch.cuda.get_device_name(0) if a.device.startswith('cuda') else '-'}")
print(f"stems={list(stems)} load+model={t1-t0:.1f}s separate={t2-t1:.1f}s total={time.time()-t0:.1f}s")
if a.device.startswith("cuda"):
    print(f"max_vram={torch.cuda.max_memory_allocated()/2**30:.2f} GiB")
