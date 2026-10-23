"""Synthetic video: red → (1 s dissolve at 2.0 to 3.0) → blue → hard cut at 5.0 → green.
Expected: one soft transition centered near 2.5 s, and the hard cut at 5.0 is NOT reported."""
import shutil
import subprocess

import pytest

from vpc.dissolve import DissolveParams, find_dissolves, frame_series

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    out = tmp_path_factory.mktemp("vid") / "synthetic.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "lavfi", "-i", "color=c=red:s=320x180:r=25:d=3",
           "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=25:d=3",
           "-f", "lavfi", "-i", "color=c=green:s=320x180:r=25:d=2",
           "-filter_complex", "[0][1]xfade=transition=fade:duration=1:offset=2[ab];[ab][2]concat=n=2:v=1:a=0[v]",
           "-map", "[v]", "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(cmd, check=True)
    return str(out)


def test_frame_series_shape(synthetic):
    f = frame_series(synthetic, 8.0)
    assert f.ndim == 3 and f.shape[1:] == (36, 64)
    assert 7 * 8 - 2 <= len(f) <= 7 * 8 + 2


def test_finds_dissolve_not_hard_cut(synthetic):
    p = DissolveParams()
    found = find_dissolves(frame_series(synthetic, p.fps), p)
    assert len(found) == 1, found
    assert abs(found[0] - 2.5) <= 0.4, found
    assert all(abs(t - 5.0) > 0.5 for t in found)


@pytest.fixture(scope="module")
def moving(tmp_path_factory):
    """Moving test pattern → 1.5 s dissolve (3.0 to 4.5) → static bars → hard cut at 6.5 → moving pattern."""
    out = tmp_path_factory.mktemp("vid") / "moving.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "lavfi", "-i", "testsrc=s=320x180:r=25:d=4",
           "-f", "lavfi", "-i", "smptebars=s=320x180:r=25:d=4",
           "-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=3",
           "-filter_complex", "[0][1]xfade=transition=dissolve:duration=1.5:offset=3[ab];[ab][2]concat=n=2:v=1:a=0[v]",
           "-map", "[v]", "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(cmd, check=True)
    return str(out)


def test_motion_inside_scene_is_not_a_transition(moving):
    p = DissolveParams()
    found = find_dissolves(frame_series(moving, p.fps), p)
    assert len(found) == 1, found
    assert abs(found[0] - 3.75) <= 0.3, found


def test_known_cuts_are_excluded(synthetic):
    p = DissolveParams()
    found = find_dissolves(frame_series(synthetic, p.fps), p, known_cuts=[2.5])
    assert found == []
