"""More aggressive experiments: RC=0/1, exit buffer, lift cap interaction."""
import re, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
R1, R2 = ROOT / "ROUND1", ROOT / "ROUND2"
SRC = R2 / "j_trader5.py"
PEP = re.compile(r"INTARIAN_PEPPER_ROOT:\s*([\-0-9,]+)")
OSM = re.compile(r"ASH_COATED_OSMIUM:\s*([\-0-9,]+)")

def run(rd, src, days, m):
    dst = rd / "_tm.py"; dst.write_text(src)
    cmd = ["prosperity4bt", str(dst), *days, "--merge-pnl", "--no-out",
           "--match-trades", m, "--data", str(rd / "data")]
    o = subprocess.run(cmd, capture_output=True, text=True).stdout
    dst.unlink()
    return (sum(int(x.replace(",","")) for x in OSM.findall(o)),
            sum(int(x.replace(",","")) for x in PEP.findall(o)))

def sweep(label, changes):
    p = base
    for pat, rep in changes.items():
        p = re.sub(pat, rep, p, count=1, flags=re.M)
    rows = {}
    for m in ["worse","none"]:
        o = pe = 0
        for rd, d in [(R1,["1--2","1--1","1-0"]),(R2,["2--1","2-0","2-1"])]:
            oo,pp = run(rd, p, d, m); o+=oo; pe+=pp
        rows[m] = (o, pe, o+pe)
    print(f"{label:<35} "
          f"w_osm={rows['worse'][0]:>7,} w_pep={rows['worse'][1]:>7,} w_all={rows['worse'][2]:>8,}  "
          f"n_osm={rows['none'][0]:>7,} n_pep={rows['none'][1]:>7,} n_all={rows['none'][2]:>8,}",
          flush=True)

base = SRC.read_text()
print("Baseline: current j_trader5 (RC=2, deep=0, penny=40, k=7)")
for a in [0.1, 0.15, 0.2, 0.25, 0.3]:
    for rc in [2, 3, 4, 5]:
        sweep(f"α={a}, RC={rc}", {
            r"^OSMIUM_EMA_ALPHA\s*=\s*[0-9.]+": f"OSMIUM_EMA_ALPHA = {a}",
            r"^OSMIUM_REGIME_CAP\s*=\s*\d+": f"OSMIUM_REGIME_CAP = {rc}",
        })
