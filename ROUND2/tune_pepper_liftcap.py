"""Sweep PEPPER_LIFT_CAP_OVER_FAIR under worse and none modes."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R1 = ROOT / "ROUND1"
R2 = ROOT / "ROUND2"
SRC = R2 / "j_trader5.py"
TMP = "_liftcap_tune.py"

PEPPER_RE = re.compile(r"INTARIAN_PEPPER_ROOT:\s*([\-0-9,]+)")


def run(round_dir: Path, patched: str, days: list[str], match: str) -> int:
    dst = round_dir / TMP
    dst.write_text(patched)
    cmd = ["prosperity4bt", str(dst), *days, "--merge-pnl", "--no-out",
           "--match-trades", match, "--data", str(round_dir / "data")]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    dst.unlink()
    return sum(int(m.replace(",", "")) for m in PEPPER_RE.findall(out))


def main() -> None:
    base = SRC.read_text()
    print(f"{'CAP':>3}  {'worse pep':>10}  {'none pep':>10}  {'all pep':>10}")
    print("-" * 50)
    for cap in [3, 5, 7, 9, 12, 15, 20, 50]:
        patched = re.sub(r"^PEPPER_LIFT_CAP_OVER_FAIR\s*=\s*\d+",
                         f"PEPPER_LIFT_CAP_OVER_FAIR = {cap}", base, count=1,
                         flags=re.M)
        rows = {}
        for m in ["worse", "none", "all"]:
            r1 = run(R1, patched, ["1--2", "1--1", "1-0"], m)
            r2 = run(R2, patched, ["2--1", "2-0", "2-1"], m)
            rows[m] = r1 + r2
        print(f"{cap:>3}  {rows['worse']:>10,}  {rows['none']:>10,}  "
              f"{rows['all']:>10,}", flush=True)


if __name__ == "__main__":
    main()
