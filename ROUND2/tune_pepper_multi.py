"""Sweep pepper MM_FLOOR, ASK_OVER_FAIR, LIFT_CAP jointly under worse/none/all."""
import re, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
R1, R2 = ROOT / "ROUND1", ROOT / "ROUND2"
SRC = R2 / "j_trader5.py"
PEP_RE = re.compile(r"INTARIAN_PEPPER_ROOT:\s*([\-0-9,]+)")

def run(rd, src, days, m):
    dst = rd / "_pep_tune.py"
    dst.write_text(src)
    cmd = ["prosperity4bt", str(dst), *days, "--merge-pnl", "--no-out",
           "--match-trades", m, "--data", str(rd / "data")]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    dst.unlink()
    return sum(int(x.replace(",","")) for x in PEP_RE.findall(out))

base = SRC.read_text()
# Test configs: (mm_floor, ask_over_fair, lift_cap).
configs = [("k={}, floor={}".format(k, f), {"floor": f, "k": k, "cap": 7})
    for k in [5, 6, 7, 8, 9, 10, 12, 15]
    for f in [30, 50, 65]]
print(f"{'config':<28} {'worse':>10} {'none':>10} {'all':>10}")
print("-"*62)
for name, c in configs:
    p = base
    p = re.sub(r"^PEPPER_MM_FLOOR\s*=\s*\d+", f"PEPPER_MM_FLOOR = {c['floor']}", p, count=1, flags=re.M)
    p = re.sub(r"^PEPPER_ASK_OVER_FAIR\s*=\s*\d+", f"PEPPER_ASK_OVER_FAIR = {c['k']}", p, count=1, flags=re.M)
    p = re.sub(r"^PEPPER_LIFT_CAP_OVER_FAIR\s*=\s*\d+", f"PEPPER_LIFT_CAP_OVER_FAIR = {c['cap']}", p, count=1, flags=re.M)
    rows = {}
    for m in ["worse","none","all"]:
        r1 = run(R1, p, ["1--2","1--1","1-0"], m)
        r2 = run(R2, p, ["2--1","2-0","2-1"], m)
        rows[m] = r1+r2
    print(f"{name:<28} {rows['worse']:>10,} {rows['none']:>10,} {rows['all']:>10,}", flush=True)
