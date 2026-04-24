"""Sweep OSMIUM_EMA_ALPHA on j_trader3 against round 2 data.

Writes a temp copy of j_trader3.py per alpha, runs prosperity4bt, parses the
per-day ASH_COATED_OSMIUM line from stdout, and prints a sorted summary.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "j_trader3.py")
TMP = os.path.join(HERE, "_tune_trader.py")
DAYS = ["2--1", "2-0", "2-1"]

ALPHAS = [0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30,
          0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.0]

ALPHA_RE = re.compile(r"^OSMIUM_EMA_ALPHA\s*=\s*[0-9.]+", re.M)
OSMIUM_RE = re.compile(r"ASH_COATED_OSMIUM:\s*([\-0-9,]+)")


def run_alpha(alpha: float) -> list[int]:
    src = open(SRC).read()
    patched = ALPHA_RE.sub(f"OSMIUM_EMA_ALPHA = {alpha}", src, count=1)
    with open(TMP, "w") as f:
        f.write(patched)

    cmd = ["prosperity4bt", TMP, *DAYS, "--merge-pnl", "--no-out",
           "--data", os.path.join(HERE, "data")]
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE).stdout
    vals = [int(m.replace(",", "")) for m in OSMIUM_RE.findall(out)]
    if len(vals) != len(DAYS):
        sys.stderr.write(f"alpha={alpha}: got {len(vals)} osmium lines, expected {len(DAYS)}\n")
        sys.stderr.write(out + "\n")
    return vals


def main() -> None:
    results: list[tuple[float, list[int], int]] = []
    for a in ALPHAS:
        vals = run_alpha(a)
        total = sum(vals)
        results.append((a, vals, total))
        print(f"alpha={a:>5}: days={vals}  total={total:,}", flush=True)

    if os.path.exists(TMP):
        os.remove(TMP)

    print("\nSorted by total osmium PnL:")
    for a, vals, total in sorted(results, key=lambda r: -r[2]):
        print(f"  alpha={a:>5}  total={total:>8,}  per-day={vals}")


if __name__ == "__main__":
    main()
