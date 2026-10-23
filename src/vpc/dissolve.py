"""Soft transition (dissolve, fade) detection.

eyes finds hard cuts: a single frame that differs sharply from its neighbours. A dissolve
spreads the same change over 0.5 to 2 seconds, so no single frame spikes and eyes reports
nothing (0 of 8 on its own explainer video). This module compares frames a window apart
instead of adjacent frames, and requires the picture to be stable on both sides of the
window, so camera motion and animation inside a scene do not count.

Scale free rule: a window [i, i+k] is a soft transition when
  change   = diff(f[i], f[i+k])          is above `change`
  before   = diff(f[i-k], f[i])          is below max(stable, stable_share * change)
  after    = diff(f[i+k], f[i+2k])       is below the same bound
  no single step inside the window carries more than `hard_share` of the change
    (otherwise it is a hard cut, which eyes already reports).
The reported time is where half of the change inside the window has happened.
Frames are 64x36 grayscale, read straight from ffmpeg at `fps` frames per second.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

import numpy as np

W, H = 64, 36


@dataclass
class DissolveParams:
    fps: float = 8.0
    windows: tuple[float, ...] = (0.5, 1.0, 2.0)   # seconds
    change: float = 0.08      # mean |Δ| over 0..1 luminance across the window
    stable: float = 0.03      # mean |Δ| allowed on each side (absolute floor)
    stable_share: float = 0.3 # or this share of the change, whichever is larger
    hard_share: float = 0.6   # one frame step carrying this share of the change = hard cut
    min_gap: float = 1.0      # seconds between reported transitions
    exclude_near_cuts: float = 0.5  # drop a transition this close to a known hard cut


def frame_series(media: str, fps: float = 8.0) -> np.ndarray:
    """(n, H, W) float32 array of luminance in 0..1."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg not found")
    cmd = [ffmpeg, "-v", "error", "-i", media, "-an", "-sn",
           "-vf", f"fps={fps},scale={W}:{H},format=gray", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = len(raw) // (W * H)
    return np.frombuffer(raw[: n * W * H], dtype=np.uint8).reshape(n, H, W).astype(np.float32) / 255.0


def _diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a - b).mean())


def find_dissolves(frames: np.ndarray, p: DissolveParams, known_cuts: list[float] | None = None) -> list[float]:
    """Center times (seconds) of soft transitions."""
    n = len(frames)
    if n < 4:
        return []
    step = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))  # per frame step, length n-1
    candidates: list[tuple[float, float]] = []                 # (score, center_time)
    for w in p.windows:
        k = max(2, int(round(w * p.fps)))
        for i in range(k, n - 2 * k):
            change = _diff(frames[i], frames[i + k])
            if change < p.change:
                continue
            # Sides must be calm relative to the change: absolute floor for static footage,
            # a share of the change for footage with constant small motion (talking heads).
            calm = max(p.stable, p.stable_share * change)
            if _diff(frames[i - k], frames[i]) > calm or _diff(frames[i + k], frames[i + 2 * k]) > calm:
                continue
            if step[i:i + k].max() > p.hard_share * change:
                continue
            # Center: where half of the change inside the window has happened.
            cum = np.cumsum(step[i:i + k])
            half = int(np.searchsorted(cum, cum[-1] / 2)) if cum[-1] > 0 else k // 2
            candidates.append((change, (i + half + 0.5) / p.fps))
    out: list[float] = []
    for score, t in sorted(candidates, reverse=True):
        if any(abs(t - o) < p.min_gap for o in out):
            continue
        if known_cuts and any(abs(t - c) < p.exclude_near_cuts for c in known_cuts):
            continue
        out.append(round(t, 2))
    return sorted(out)


def detect(media: str, p: DissolveParams | None = None, known_cuts: list[float] | None = None) -> list[float]:
    p = p or DissolveParams()
    return find_dissolves(frame_series(media, p.fps), p, known_cuts)
