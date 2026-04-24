"""Sweep OSMIUM_INSIDE_CAP across match modes on both rounds."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R1 = ROOT / "ROUND1"
R2 = ROOT / "ROUND2"
SRC = R2 / "j_trader5.py"
TMP = "_inside_tune.py"

PEPPER_RE = re.compile(r"INTARIAN_PEPPER_ROOT:\s*([\-0-9,]+)")
OSMIUM_RE = re.compile(r"ASH_COATED_OSMIUM:\s*([\-0-9,]+)")


def run(round_dir: Path, patched: str, days: list[str], match: str) -> tuple[int, int]:
    dst = round_dir / TMP
    dst.write_text(patched)
    cmd = ["prosperity4bt", str(dst), *days, "--merge-pnl", "--no-out",
           "--match-trades", match, "--data", str(round_dir / "data")]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    dst.unlink()
    p = sum(int(m.replace(",", "")) for m in PEPPER_RE.findall(out))
    o = sum(int(m.replace(",", "")) for m in OSMIUM_RE.findall(out))
    return p, o


def main() -> None:
    base = SRC.read_text()
    print(f"{'CAP':>3}  "
          f"{'worse osm':>10}  {'none osm':>10}  {'all osm':>10}  "
          f"{'worse Δ':>8}  {'none Δ':>8}")
    print("-" * 70)
    # Baseline (no inside tier): CAP=0.
    for cap in [0, 2, 4, 6, 8, 10, 15, 20]:
        patched = re.sub(r"^OSMIUM_INSIDE_CAP\s*=\s*\d+",
                         f"OSMIUM_INSIDE_CAP = {cap}", base, count=1, flags=re.M)
        rows = {}
        for m in ["worse", "none", "all"]:
            _, o1 = run(R1, patched, ["1--2", "1--1", "1-0"], m)
            _, o2 = run(R2, patched, ["2--1", "2-0", "2-1"], m)
            rows[m] = o1 + o2
        print(f"{cap:>3}  {rows['worse']:>10,}  {rows['none']:>10,}  "
              f"{rows['all']:>10,}", flush=True)


if __name__ == "__main__":
    main()
