from pathlib import Path

from vpc.cache import Index
from vpc.checks import (Thresholds, cuts_in_words, normalize, pace_windows, run_checks, script_diff, silences)

W = [  # 4 Hebrew words, a 3.6 s hole between the second and third
    {"start": 0.0, "end": 0.4, "text": "שלום"},
    {"start": 0.5, "end": 0.9, "text": "לכולם,"},
    {"start": 4.5, "end": 4.9, "text": "הַיּוֹם"},
    {"start": 5.0, "end": 5.5, "text": "נדבר"},
]


def test_normalize_strips_niqqud_and_punctuation():
    assert normalize("הַיּוֹם, לכולם!") == ["היום", "לכולם"]


def test_silences():
    assert silences(W, 2.5) == [(0.9, 3.6)]
    assert silences(W, 5.0) == []


def test_cuts_in_words_respects_margin():
    assert cuts_in_words(W, [0.7, 5.02, 3.0], margin=0.08) == [(0.7, "לכולם,")]


def test_pace_windows_needs_ten_seconds():
    assert pace_windows(W, 30, 15) == []
    long = [{"start": i * 0.4, "end": i * 0.4 + 0.3, "text": "מילה"} for i in range(100)]
    wins = pace_windows(long, 30, 15)
    assert wins and all(140 <= v <= 160 for _, v in wins)


def test_script_diff_reports_missing_run_with_timestamp():
    ratio, missing, extra = script_diff(W, "שלום לכולם היום נדבר על קלוד ועל וידאו ארוך", 3)
    assert missing == [(5.5, "על קלוד ועל וידאו ארוך")]
    assert extra == []
    assert 0.5 < ratio < 1


def test_run_checks_assembles_findings_in_time_order():
    idx = Index(vdir=Path("."), duration=6.0, words=W, cuts=[0.7], lufs=-18.0, true_peak=0.5)
    res = run_checks(idx, Thresholds(), "שלום לכולם היום נדבר", dissolves=[3.0])
    kinds = [f.kind for f in res.findings]
    assert kinds == ["loudness", "peak", "cut-in-word", "silence", "dissolve"]
    assert all(res.findings[i].t <= res.findings[i + 1].t for i in range(len(res.findings) - 1))
    assert any("תואם לתסריט" in p for p in res.passed)


def test_run_checks_without_words_skips_not_crashes():
    idx = Index(vdir=Path("."), duration=6.0, words=[], cuts=[1.0], lufs=-14.0)
    res = run_checks(idx, Thresholds(), None)
    assert res.findings == []
    assert len(res.skipped) == 2
