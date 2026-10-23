"""Read the claude-eyes cache directly.

eyes stores one folder per indexed video under ~/.cache/eyes/<id>/ (override: EYES_HOME):
meta.json, shots.json, transcript.json, audio.json, source.json. Reading those files is
more reliable than parsing CLI output, and the schema is documented here in one place.

transcript.json  {"source", "segments": [{start,end,text}], "word_timings": [{start,end,text}],
                  "words_per_minute", "speech_coverage"}
shots.json       {"shots": [{"i", "start", "end", "len"}]}   cuts are the starts of shots[1:]
audio.json       {"lufs", "true_peak", "lra", "silence_share", ...}
meta.json        {"duration", "width", "height", "fps", "orientation", "has_audio"}
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

HOME = Path(os.environ.get("EYES_HOME", Path.home() / ".cache" / "eyes")).expanduser()


@dataclass
class Index:
    vdir: Path
    duration: float
    words: list[dict] = field(default_factory=list)      # [{start,end,text}]
    segments: list[dict] = field(default_factory=list)   # [{start,end,text}]
    cuts: list[float] = field(default_factory=list)
    lufs: float | None = None
    true_peak: float | None = None
    transcript_source: str | None = None
    media: str | None = None

    @property
    def wpm(self) -> float | None:
        if not self.words:
            return None
        span = self.words[-1]["end"] - self.words[0]["start"]
        return len(self.words) * 60.0 / span if span > 0 else None


def _read(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def eyes_binary() -> str | None:
    return shutil.which("eyes")


def resolve(ref: str) -> Path:
    """Cache folder for an indexed video, by id, id prefix, original path or URL."""
    try:
        from eyes.common import resolve as _resolve  # type: ignore
        return _resolve(ref)
    except ImportError:
        pass
    lib = _read(HOME / "library.json", {}) or {}
    lib = {vid: e for vid, e in lib.items() if (HOME / vid).is_dir()}
    if ref in lib:
        return HOME / ref
    p = Path(ref).expanduser()
    if p.exists():
        target = str(p.resolve())
        for vid, e in lib.items():
            if e.get("source") == target:
                return HOME / vid
    matches = [vid for vid in lib if vid.startswith(ref.lower())] or [vid for vid in lib if ref.lower() in vid]
    if len(matches) == 1:
        return HOME / matches[0]
    raise SystemExit(f"{ref!r} is not indexed. Run: eyes index \"{ref}\"")


def index_video(source: str, *, lang: str | None, glossary: str | None, transcriber: str | None,
                force: bool = False) -> None:
    """Run `eyes index` (cached; instant when already indexed)."""
    binary = eyes_binary()
    if not binary:
        raise SystemExit("eyes is not installed. Run: uv tool install git+https://github.com/moritzkremb/claude-eyes")
    cmd = [binary, "index", source]
    if lang:
        cmd += ["--lang", lang]
    if glossary:
        cmd += ["--glossary", glossary]
    if transcriber:
        cmd += ["--transcriber", transcriber]
    if force:
        cmd.append("--force")
    result = subprocess.run(cmd, text=True)
    if result.returncode != 0:
        raise SystemExit(f"eyes index failed (exit {result.returncode})")


def load(ref: str) -> Index:
    vdir = resolve(ref)
    meta = _read(vdir / "meta.json", {}) or {}
    tr = _read(vdir / "transcript.json", {}) or {}
    shots = (_read(vdir / "shots.json", {}) or {}).get("shots", [])
    audio = _read(vdir / "audio.json", {}) or {}
    src = _read(vdir / "source.json", {}) or {}
    words = [{"start": float(w["start"]), "end": float(w["end"]), "text": str(w["text"]).strip()}
             for w in tr.get("word_timings") or [] if str(w.get("text", "")).strip()]
    return Index(
        vdir=vdir,
        duration=float(meta.get("duration") or (shots[-1]["end"] if shots else 0.0)),
        words=words,
        segments=tr.get("segments") or [],
        cuts=[float(s["start"]) for s in shots[1:]],
        lufs=audio.get("lufs"),
        true_peak=audio.get("true_peak"),
        transcript_source=tr.get("source"),
        media=src.get("media"),
    )
