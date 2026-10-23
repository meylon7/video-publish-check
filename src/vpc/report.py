"""Hebrew markdown report and JSON sidecar."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .cache import Index
from .checks import Result, fmt

NOT_CHECKED = "איכות הקליפים עצמם (אצבעות, פנים, תנועה לא טבעית): דורש צפייה אנושית"


def render_md(name: str, idx: Index, res: Result, dissolves: list[float]) -> str:
    wpm = f"{idx.wpm:.0f}" if idx.wpm else "אין"
    lufs = f"{idx.lufs:.1f}" if idx.lufs is not None else "אין"
    lines = [f"# בדיקה לפני פרסום: {name}",
             f"אורך: {fmt(idx.duration)} | מילים לדקה: {wpm} | LUFS: {lufs} | "
             f"חיתוכים: {len(idx.cuts)} | מעברים רכים: {len(dissolves)} | תמלול: {idx.transcript_source or 'אין'}",
             "", "## תיקונים (לפי סדר זמן)"]
    if res.findings:
        for i, f in enumerate(res.findings, 1):
            tag = " 👁" if f.needs_eyes else ""
            lines.append(f"{i}. [{fmt(f.t)}] {f.message}{tag}")
        if any(f.needs_eyes for f in res.findings):
            lines += ["", "👁 = לבדוק בפריים לפני שמשאירים ברשימה (eyes frames --at, eyes burst)"]
    else:
        lines.append("אין ממצאים מספריים.")
    lines += ["", "## עבר בהצלחה"] + ([f"- {p}" for p in res.passed] or ["- (כלום עדיין)"])
    lines += ["", "## לא נבדק", f"- {NOT_CHECKED}"] + [f"- {s}" for s in res.skipped]
    return "\n".join(lines) + "\n"


def write(out: Path, name: str, idx: Index, res: Result, dissolves: list[float]) -> str:
    md = render_md(name, idx, res, dissolves)
    out.write_text(md, encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps({
        "render": name, "duration": idx.duration, "wpm": idx.wpm, "lufs": idx.lufs, "true_peak": idx.true_peak,
        "cuts": idx.cuts, "dissolves": dissolves, "transcript_source": idx.transcript_source,
        "findings": [asdict(f) for f in res.findings], "passed": res.passed, "skipped": res.skipped,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return md
