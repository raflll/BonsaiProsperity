import re, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
R1, R2 = ROOT / "ROUND1", ROOT / "ROUND2"
SRC = R2 / "j_trader5.py"
OSM_RE = re.compile(r"ASH_COATED_OSMIUM:\s*([\-0-9,]+)")
PEP_RE = re.compile(r"INTARIAN_PEPPER_ROOT:\s*([\-0-9,]+)")

def run(rd, src, days, m):
    dst = rd / "_rc_tune.py"
    dst.write_text(src)
    cmd = ["prosperity4bt", str(dst), *days, "--merge-pnl", "--no-out",
           "--match-trades", m, "--data", str(rd / "data")]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    dst.unlink()
    return (sum(int(x.replace(",","")) for x in OSM_RE.findall(out)),
            sum(int(x.replace(",","")) for x in PEP_RE.findall(out)))

base = SRC.read_text()
print(f"{'RC':>3}  {'worse osm':>10} {'worse pep':>10} {'worse all':>11}  "
      f"{'none osm':>9} {'all osm':>9}")
print("-"*70)
for rc in [1, 2, 3, 4, 5, 6, 8, 10]:
    p = re.sub(r"^OSMIUM_REGIME_CAP\s*=\s*\d+", f"OSMIUM_REGIME_CAP = {rc}",
               base, count=1, flags=re.M)
    o_w, pe_w = 0, 0
    for rd, days in [(R1, ["1--2","1--1","1-0"]), (R2, ["2--1","2-0","2-1"])]:
        o, pe = run(rd, p, days, "worse")
        o_w += o; pe_w += pe
    # Also none and all osmium
    o_n = 0; o_a = 0
    for rd, days in [(R1, ["1--2","1--1","1-0"]), (R2, ["2--1","2-0","2-1"])]:
        o, _ = run(rd, p, days, "none"); o_n += o
        o, _ = run(rd, p, days, "all"); o_a += o
    print(f"{rc:>3}  {o_w:>10,} {pe_w:>10,} {o_w+pe_w:>11,}  "
          f"{o_n:>9,} {o_a:>9,}", flush=True)
