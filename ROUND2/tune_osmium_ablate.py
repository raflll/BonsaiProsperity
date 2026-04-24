"""Ablate osmium components to find what hurts vs helps."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R1 = ROOT / "ROUND1"
R2 = ROOT / "ROUND2"
SRC = R2 / "j_trader5.py"
TMP = "_ablate.py"

OSM_RE = re.compile(r"ASH_COATED_OSMIUM:\s*([\-0-9,]+)")


def run(round_dir: Path, patched: str, days: list[str], match: str) -> int:
    dst = round_dir / TMP
    dst.write_text(patched)
    cmd = ["prosperity4bt", str(dst), *days, "--merge-pnl", "--no-out",
           "--match-trades", match, "--data", str(round_dir / "data")]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    dst.unlink()
    return sum(int(m.replace(",", "")) for m in OSM_RE.findall(out))


def apply(src: str, changes: dict) -> str:
    """changes: dict of regex → replacement (all count=1, multiline)."""
    for pat, rep in changes.items():
        src = re.sub(pat, rep, src, count=1, flags=re.M)
    return src


def main() -> None:
    base = SRC.read_text()

    # Baseline is current j_trader5.
    configs = [
        ("baseline (current)", {}),
        ("inside=0 only", {r"^OSMIUM_INSIDE_CAP\s*=\s*\d+": "OSMIUM_INSIDE_CAP = 0"}),
        ("deep=5, inside=0", {
            r"^OSMIUM_DEEP_CAP\s*=\s*\d+": "OSMIUM_DEEP_CAP = 5",
            r"^OSMIUM_INSIDE_CAP\s*=\s*\d+": "OSMIUM_INSIDE_CAP = 0",
        }),
        ("penny=60, inside=20", {
            r"^OSMIUM_PENNY_CAP\s*=\s*\d+": "OSMIUM_PENNY_CAP = 60",
            r"^OSMIUM_INSIDE_CAP\s*=\s*\d+": "OSMIUM_INSIDE_CAP = 20",
        }),
        ("penny=80, inside=30", {
            r"^OSMIUM_PENNY_CAP\s*=\s*\d+": "OSMIUM_PENNY_CAP = 80",
            r"^OSMIUM_INSIDE_CAP\s*=\s*\d+": "OSMIUM_INSIDE_CAP = 30",
        }),
        ("α=0.2", {r"^OSMIUM_EMA_ALPHA\s*=\s*[0-9.]+": "OSMIUM_EMA_ALPHA = 0.2"}),
        ("α=0.6", {r"^OSMIUM_EMA_ALPHA\s*=\s*[0-9.]+": "OSMIUM_EMA_ALPHA = 0.6"}),
        ("α=1.0 (mid=fair)", {r"^OSMIUM_EMA_ALPHA\s*=\s*[0-9.]+": "OSMIUM_EMA_ALPHA = 1.0"}),
        ("regime_cap=3", {r"^OSMIUM_REGIME_CAP\s*=\s*\d+": "OSMIUM_REGIME_CAP = 3"}),
        ("regime_cap=20", {r"^OSMIUM_REGIME_CAP\s*=\s*\d+": "OSMIUM_REGIME_CAP = 20"}),
    ]
    print(f"{'config':<28} {'worse':>8} {'none':>8} {'all':>8}")
    print("-" * 60)
    for name, changes in configs:
        patched = apply(base, changes)
        rows = {}
        for m in ["worse", "none", "all"]:
            r1 = run(R1, patched, ["1--2", "1--1", "1-0"], m)
            r2 = run(R2, patched, ["2--1", "2-0", "2-1"], m)
            rows[m] = r1 + r2
        print(f"{name:<28} {rows['worse']:>8,} {rows['none']:>8,} "
              f"{rows['all']:>8,}", flush=True)


if __name__ == "__main__":
    main()
