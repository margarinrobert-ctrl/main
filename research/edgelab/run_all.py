"""DISCOVER US100 EDGE -- the whole pipeline in one command (brief section 52).

    python3 research/edgelab/run_all.py

Stages run in the brief's order and each prints as it completes. The production block is read
only in the final stage, once.
"""
from __future__ import annotations

import subprocess
import sys
import time

STAGES = [
    ("LOAD + VALIDATE DATA, CLOCK CHECK", "from edgelab import data; data.verify_clock(); print(); data.audit()"),
    ("LEAKAGE AUDIT", "from edgelab import data, audit; audit.run(data.bars(15))"),
    ("DESCRIPTIVE SWEEPS (time of day, stop, target, hold, excursions)",
     "import runpy; runpy.run_path('research/edgelab/_desc.py')"),
]


def sh(code):
    return subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0,'research')\n" + code],
                          check=False).returncode


def main():
    t0 = time.time()
    for i, (name, code) in enumerate(STAGES, 1):
        print(f"\n{'='*90}\n[{i}/{len(STAGES)+3}] {name}\n{'='*90}", flush=True)
        sh(code)
    for i, script in enumerate(("run_discovery", "run_validate", "run_report"), len(STAGES) + 1):
        print(f"\n{'='*90}\n[{i}/{len(STAGES)+3}] {script.replace('_',' ').upper()}\n{'='*90}", flush=True)
        subprocess.run([sys.executable, f"research/edgelab/{script}.py"], check=False)
    print(f"\nfinished in {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
