"""Joint sweep of osmium caps + EMA alpha under all match modes."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R1 = ROOT / "ROUND1"
R2 = ROOT / "ROUND2"
SRC = R2 / "j_trader5.py"
TMP = "_osm_tune.py"

OSM_RE = re.compile(r"ASH_COATED_OSMIUM:\s*([\-0-9,]+)")


def run(round_dir: Path, patched: str, days: list[str], match: str) -> int:
    dst = round_dir / TMP
    dst.write_text(patched)
    cmd = ["prosperity4bt", str(dst), *days, "--merge-pnl", "--no-out",
           "--match-trades", match, "--data", str(round_dir / "data")]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    dst.unlink()
    return sum(int(m.replace(",", "")) for m in OSM_RE.findall(out))


def main() -> None:
    base = SRC.read_text()
    grids = [
        # (penny, deep, inside)
        (25, 15, 8),    # current
        (40, 25, 10),   # bigger
        (60, 40, 15),   # much bigger
        (80, 50, 20),   # max-ish
        (40, 0, 15),    # no deep, penny+inside only
        (80, 0, 20),    # massive penny+inside
    ]
    alphas = [0.1, 0.2, 0.4, 0.6]
    print(f"{'penny':>5} {'deep':>4} {'inside':>6} {'α':>5}  "
          f"{'worse':>8} {'none':>8} {'all':>8}")
    print("-" * 60)
    for penny, deep, inside in grids:
        for a in alphas:
            patched = base
            patched = re.sub(r"^OSMIUM_PENNY_CAP\s*=\s*\d+",
                             f"OSMIUM_PENNY_CAP = {penny}", patched, count=1, flags=re.M)
            patched = re.sub(r"^OSMIUM_DEEP_CAP\s*=\s*\d+",
                             f"OSMIUM_DEEP_CAP = {deep}", patched, count=1, flags=re.M)
            patched = re.sub(r"^OSMIUM_INSIDE_CAP\s*=\s*\d+",
                             f"OSMIUM_INSIDE_CAP = {inside}", patched, count=1, flags=re.M)
            patched = re.sub(r"^OSMIUM_EMA_ALPHA\s*=\s*[0-9.]+",
                             f"OSMIUM_EMA_ALPHA = {a}", patched, count=1, flags=re.M)
            rows = {}
            for m in ["worse", "none", "all"]:
                r1 = run(R1, patched, ["1--2", "1--1", "1-0"], m)
                r2 = run(R2, patched, ["2--1", "2-0", "2-1"], m)
                rows[m] = r1 + r2
            print(f"{penny:>5} {deep:>4} {inside:>6} {a:>5}  "
                  f"{rows['worse']:>8,} {rows['none']:>8,} {rows['all']:>8,}",
                  flush=True)


if __name__ == "__main__":
    main()
