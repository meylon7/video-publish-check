"""Numeric checks on an eyes Index. Pure functions; no I/O, so each one is unit testable."""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .cache import Index

NIQQUD = re.compile(r"[֑-ׇ]")
NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)


@dataclass
class Thresholds:
    wpm_min: float = 110.0
    wpm_max: float = 160.0
    window: float = 30.0          # pace window in seconds
    gap: float = 2.5              # silence between words, seconds
    lufs_target: float = -14.0
    lufs_tol: float = 1.5
    true_peak_max: float = -1.0   # dBTP
    cut_margin: float = 0.08      # seconds inside a word before a cut counts
    diff_min_run: int = 3         # words in a row before a script mismatch is reported


@dataclass
class Finding:
    t: float                      # seconds
    kind: str                     # pace-fast, pace-slow, silence, cut-in-word, loudness, peak, script-missing, script-extra, dissolve
    message: str                  # Hebrew, one line: problem → action
    needs_eyes: bool = False      # true when the agent must look at frames before keeping it


@dataclass
class Result:
    findings: list[Finding] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def fmt(t: float) -> str:
    m, s = divmod(int(round(t)), 60)
    return f"{m}:{s:02d}"


# ---------- words ----------

def normalize(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text)
    text = NIQQUD.sub("", text)
    text = NON_WORD.sub(" ", text)
    return [w for w in text.lower().split() if w]


def pace_windows(words: list[dict], window: float, step: float) -> list[tuple[float, float]]:
    """(window start, words per minute) for every window with at least 10 s of coverage."""
    if not words:
        return []
    end = words[-1]["end"]
    out, t = [], 0.0
    while t < end:
        span = min(window, end - t)
        if span >= 10:
            n = sum(1 for w in words if t <= w["start"] < t + window)
            out.append((t, n * 60.0 / span))
        t += step
    return out


def silences(words: list[dict], gap: float) -> list[tuple[float, float]]:
    return [(a["end"], b["start"] - a["end"]) for a, b in zip(words, words[1:]) if b["start"] - a["end"] >= gap]


def cuts_in_words(words: list[dict], cuts: list[float], margin: float) -> list[tuple[float, str]]:
    out = []
    for c in cuts:
        for w in words:
            if w["start"] + margin < c < w["end"] - margin:
                out.append((c, w["text"]))
                break
    return out


def script_diff(words: list[dict], script_text: str, min_run: int):
    """Runs of >= min_run script words never spoken, and spoken runs not in the script."""
    script_words = normalize(script_text)
    flat, index = [], []
    for i, w in enumerate(words):
        for tok in normalize(w["text"]):
            flat.append(tok)
            index.append(i)
    sm = difflib.SequenceMatcher(a=script_words, b=flat, autojunk=False)
    missing, extra = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        at = words[index[j1]]["start"] if j1 < len(index) else (words[-1]["end"] if words else 0.0)
        if i2 - i1 >= min_run:
            missing.append((at, " ".join(script_words[i1:i2])))
        if j2 - j1 >= min_run:
            extra.append((at, " ".join(flat[j1:j2])))
    return sm.ratio(), missing, extra


# ---------- assembly ----------

def run_checks(idx: Index, th: Thresholds, script_text: str | None = None,
               dissolves: list[float] | None = None) -> Result:
    r = Result()
    words = idx.words

    if words:
        wins = pace_windows(words, th.window, th.window / 2)
        fast = [(t, v) for t, v in wins if v > th.wpm_max]
        slow = [(t, v) for t, v in wins if 0 < v < th.wpm_min]
        for t, v in fast:
            r.findings.append(Finding(t, "pace-fast",
                f"קריינות מהירה: {v:.0f} מילים לדקה בחלון של {th.window:.0f} שניות → להאט את ההקלטה או לקצר את הטקסט"))
        for t, v in slow:
            r.findings.append(Finding(t, "pace-slow",
                f"קריינות איטית: {v:.0f} מילים לדקה → לבדוק גרירה או שקטים מיותרים בקטע"))
        if not fast and not slow:
            r.passed.append(f"קצב קריינות בטווח {th.wpm_min:.0f} עד {th.wpm_max:.0f} לכל האורך (ממוצע {idx.wpm:.0f})")
        for t, d in silences(words, th.gap):
            r.findings.append(Finding(t, "silence",
                f"שקט של {d:.1f} שניות → לבדוק בפריים: מעבר מכוון או חור", needs_eyes=True))
        if idx.cuts:
            hits = cuts_in_words(words, idx.cuts, th.cut_margin)
            for t, w in hits:
                r.findings.append(Finding(t, "cut-in-word",
                    f"חיתוך באמצע המילה '{w}' → להזיז את החיתוך לגבול מילה", needs_eyes=True))
            if not hits:
                r.passed.append(f"{len(idx.cuts)} חיתוכים, אף אחד לא נופל בתוך מילה")
        else:
            r.skipped.append("חיתוכים מול מילים: אין רשימת חיתוכים באינדקס")
    else:
        r.skipped.append("קצב, שקטים והתאמה לתסריט: אין תזמון מילים. הרץ eyes index עם --transcriber whisper או elevenlabs")

    if idx.lufs is not None:
        if abs(idx.lufs - th.lufs_target) > th.lufs_tol:
            r.findings.append(Finding(0.0, "loudness",
                f"עוצמה משולבת {idx.lufs:.1f} LUFS, יעד {th.lufs_target:.0f} → לנרמל את המיקס (loudnorm) לפני יצוא"))
        else:
            r.passed.append(f"עוצמה {idx.lufs:.1f} LUFS בטווח היעד")
    else:
        r.skipped.append("עוצמה: אין ערך LUFS באינדקס")
    if idx.true_peak is not None and idx.true_peak > th.true_peak_max:
        r.findings.append(Finding(0.0, "peak",
            f"שיא אמיתי {idx.true_peak:.1f} dBTP, מעל {th.true_peak_max:.0f} → להוסיף limiter"))

    if script_text is not None and words:
        ratio, missing, extra = script_diff(words, script_text, th.diff_min_run)
        for t, run in missing:
            r.findings.append(Finding(t, "script-missing", f"בתסריט אבל לא נאמר: \"{run[:80]}\" → להשלים קריינות או לעדכן תסריט"))
        for t, run in extra:
            r.findings.append(Finding(t, "script-extra", f"נאמר אבל לא בתסריט: \"{run[:80]}\" → לאשר שזה מכוון"))
        if not missing and not extra:
            r.passed.append(f"התמלול תואם לתסריט (דמיון {ratio:.0%})")
    elif script_text is None:
        r.skipped.append("התאמה לתסריט: לא ניתן תסריט (--script)")

    if dissolves:
        for t in dissolves:
            r.findings.append(Finding(t, "dissolve",
                "מעבר רך שלא נספר כחיתוך → נספר כאן; לבדוק שהוא מכוון ושהקריינות לא נופלת באמצעו", needs_eyes=True))

    r.findings.sort(key=lambda f: f.t)
    return r


def read_script(path: str | Path) -> str:
    return Path(path).expanduser().read_text(encoding="utf-8")
