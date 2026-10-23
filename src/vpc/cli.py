"""vpc: pre publish checks for a rendered video.

  vpc check RENDER [--script script.md] [--glossary "Names"] [--lang he] [--out publish-check.md]
  vpc dissolves MEDIA [--json]
  vpc install-skill [--to DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from . import __version__, cache, report
from .checks import Thresholds, read_script, run_checks
from .dissolve import DissolveParams, detect

SKILL_SRC = Path(__file__).parent / "skill" / "SKILL.md"
REPO_SKILL = Path(__file__).resolve().parents[2] / "skills" / "video-publish-check" / "SKILL.md"


def _has_elevenlabs() -> bool:
    if os.environ.get("ELEVENLABS_API_KEY"):
        return True
    try:
        return any(line.strip().removeprefix("export ").startswith("ELEVENLABS_API_KEY=")
                   for line in Path(".env").read_text(encoding="utf-8").splitlines())
    except OSError:
        return False


def cmd_check(a) -> int:
    render = str(Path(a.render).expanduser().resolve())
    transcriber = a.transcriber or ("elevenlabs" if _has_elevenlabs() else "whisper")
    if not a.no_index:
        cache.index_video(render, lang=a.lang, glossary=a.glossary, transcriber=transcriber, force=a.force)
    idx = cache.load(render)
    th = Thresholds(wpm_min=a.wpm_min, wpm_max=a.wpm_max, window=a.window, gap=a.gap,
                    lufs_target=a.lufs_target, lufs_tol=a.lufs_tol)
    script_text = read_script(a.script) if a.script else None
    dissolves: list[float] = []
    if not a.no_dissolves:
        dissolves = detect(idx.media or render, known_cuts=idx.cuts)
    res = run_checks(idx, th, script_text, dissolves)
    out = Path(a.out) if a.out else Path(render).with_name("publish-check.md")
    md = report.write(out, Path(render).name, idx, res, dissolves)
    if a.json:
        print(out.with_suffix(".json").read_text(encoding="utf-8"))
    else:
        print(md)
        print(f"[vpc] report: {out}", file=sys.stderr)
    return 0


def cmd_dissolves(a) -> int:
    p = DissolveParams(fps=a.fps)
    found = detect(a.media, p)
    if a.json:
        print(json.dumps({"media": a.media, "dissolves": found}))
    else:
        print("\n".join(f"{t:.2f}" for t in found) if found else "none")
    return 0


def cmd_install_skill(a) -> int:
    src = SKILL_SRC if SKILL_SRC.exists() else REPO_SKILL
    if not src.exists():
        raise SystemExit("SKILL.md not found in the package")
    targets = [Path(a.to).expanduser()] if a.to else [Path.home() / ".claude" / "skills"]
    for base in targets:
        dest = base / "video-publish-check" / "SKILL.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        print(f"installed {dest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vpc", description="pre publish checks for rendered videos (built on claude-eyes)")
    ap.add_argument("--version", action="version", version=f"vpc {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="index the render with eyes and write publish-check.md next to it")
    c.add_argument("render")
    c.add_argument("--script", help="script or narration text to compare the transcript against")
    c.add_argument("--glossary", help="comma separated names the narration uses, for correct spelling")
    c.add_argument("--lang", default="he")
    c.add_argument("--transcriber", choices=["whisper", "elevenlabs", "captions", "auto"],
                   help="default: elevenlabs when ELEVENLABS_API_KEY is set, else whisper")
    c.add_argument("--out")
    c.add_argument("--json", action="store_true")
    c.add_argument("--no-index", action="store_true", help="the render is already indexed; skip eyes index")
    c.add_argument("--no-dissolves", action="store_true")
    c.add_argument("--force", action="store_true", help="rebuild the eyes index")
    c.add_argument("--wpm-min", type=float, default=110)
    c.add_argument("--wpm-max", type=float, default=160)
    c.add_argument("--window", type=float, default=30)
    c.add_argument("--gap", type=float, default=2.5)
    c.add_argument("--lufs-target", type=float, default=-14)
    c.add_argument("--lufs-tol", type=float, default=1.5)
    c.set_defaults(fn=cmd_check)

    d = sub.add_parser("dissolves", help="list soft transitions (dissolve, fade) eyes does not count as cuts")
    d.add_argument("media")
    d.add_argument("--fps", type=float, default=8.0)
    d.add_argument("--json", action="store_true")
    d.set_defaults(fn=cmd_dissolves)

    s = sub.add_parser("install-skill", help="copy the skill into ~/.claude/skills (or --to DIR)")
    s.add_argument("--to")
    s.set_defaults(fn=cmd_install_skill)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
