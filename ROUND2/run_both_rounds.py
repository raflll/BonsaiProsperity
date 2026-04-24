"""Run a given trader file against round 1 and round 2 data, report pepper PnL
separately for each round so we can see whether a change generalises OOS.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R1 = ROOT / "ROUND1"
R2 = ROOT / "ROUND2"

PEPPER_RE = re.compile(r"INTARIAN_PEPPER_ROOT:\s*([\-0-9,]+)")
OSMIUM_RE = re.compile(r"ASH_COATED_OSMIUM:\s*([\-0-9,]+)")


def run(round_dir: Path, trader: str, days: list[str],
        match: str = "all") -> tuple[list[int], list[int]]:
    src = R2 / trader
    dst = round_dir / trader
    dst.write_text(src.read_text())
    cmd = ["prosperity4bt", str(dst), *days, "--merge-pnl", "--no-out",
           "--match-trades", match,
           "--data", str(round_dir / "data")]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    pepper = [int(m.replace(",", "")) for m in PEPPER_RE.findall(out)]
    osmium = [int(m.replace(",", "")) for m in OSMIUM_RE.findall(out)]
    return pepper, osmium


def main() -> None:
    trader = sys.argv[1] if len(sys.argv) > 1 else "j_trader4.py"
    match = sys.argv[2] if len(sys.argv) > 2 else "all"
    p1, o1 = run(R1, trader, ["1--2", "1--1", "1-0"], match=match)
    p2, o2 = run(R2, trader, ["2--1", "2-0", "2-1"], match=match)
    print(f"\n[{trader}, --match-trades {match}]")
    print(f"  ROUND1 pepper: {p1}  sum={sum(p1):,}")
    print(f"  ROUND2 pepper: {p2}  sum={sum(p2):,}")
    print(f"  combined pepper: {sum(p1) + sum(p2):,}")
    print(f"  ROUND1 osmium: {o1}  sum={sum(o1):,}")
    print(f"  ROUND2 osmium: {o2}  sum={sum(o2):,}")


if __name__ == "__main__":
    main()
