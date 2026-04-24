"""Sweep two pepper params in j_trader4 and report both rounds.

Generic param sweeper: accepts a list of (regex, replacement) tuples per trial
and runs the resulting trader against round 1 and round 2 pepper days.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R1 = ROOT / "ROUND1"
R2 = ROOT / "ROUND2"
SRC = R2 / "j_trader4.py"
TMP_NAME = "_pepper_tune.py"

PEPPER_RE = re.compile(r"INTARIAN_PEPPER_ROOT:\s*([\-0-9,]+)")


def patch(trials: list[tuple[str, str]]) -> str:
    src = SRC.read_text()
    for pattern, replacement in trials:
        new, n = re.subn(pattern, replacement, src, count=1, flags=re.M)
        assert n == 1, f"pattern not found: {pattern!r}"
        src = new
    return src


def run_one(round_dir: Path, patched: str, days: list[str]) -> list[int]:
    dst = round_dir / TMP_NAME
    dst.write_text(patched)
    cmd = ["prosperity4bt", str(dst), *days, "--merge-pnl", "--no-out",
           "--data", str(round_dir / "data")]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    dst.unlink()
    return [int(m.replace(",", "")) for m in PEPPER_RE.findall(out)]


def sweep() -> None:
    # Joint (K = MM ask over fair, CAP = lift cap over fair) grid. FLOOR=65.
    # Deep ask (K_DEEP, QTY_DEEP) sweep.
    deep_ks = [6, 7, 8, 9, 10]
    deep_qtys = [3, 5, 8, 12]
    print(f"{'K_DEEP':>6} {'QTY':>3}  {'R1 sum':>8}  {'R2 sum':>8}  {'both':>9}")
    print("-" * 42)
    for k in deep_ks:
        for q in deep_qtys:
            patched = patch([
                (r"^PEPPER_ASK_OVER_FAIR_DEEP\s*=\s*\d+",
                 f"PEPPER_ASK_OVER_FAIR_DEEP = {k}"),
                (r"^PEPPER_ASK_DEEP_QTY\s*=\s*\d+",
                 f"PEPPER_ASK_DEEP_QTY = {q}"),
            ])
            p1 = run_one(R1, patched, ["1--2", "1--1", "1-0"])
            p2 = run_one(R2, patched, ["2--1", "2-0", "2-1"])
            r1, r2 = sum(p1), sum(p2)
            print(f"{k:>6} {q:>3}  {r1:>8,}  {r2:>8,}  {r1 + r2:>9,}",
                  flush=True)
    return
    ks = [4, 5, 6, 7]
    caps = [0, 1, 2, 3, 4, 5]
    print(f"{'K':>3} {'CAP':>4}  {'R1 sum':>8}  {'R2 sum':>8}  {'both':>9}")
    print("-" * 42)
    for cap in caps:
        for k in ks:
            patched = patch([
                (r"^PEPPER_ASK_OVER_FAIR\s*=\s*\d+", f"PEPPER_ASK_OVER_FAIR = {k}"),
                (r"^PEPPER_LIFT_CAP_OVER_FAIR\s*=\s*\d+", f"PEPPER_LIFT_CAP_OVER_FAIR = {cap}"),
            ])
            p1 = run_one(R1, patched, ["1--2", "1--1", "1-0"])
            p2 = run_one(R2, patched, ["2--1", "2-0", "2-1"])
            r1, r2 = sum(p1), sum(p2)
            print(f"{k:>3} {cap:>4}  {r1:>8,}  {r2:>8,}  {r1 + r2:>9,}",
                  flush=True)


if __name__ == "__main__":
    sweep()
