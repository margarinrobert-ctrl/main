#!/usr/bin/env python3
"""Development launcher: ``python run.py``.

The packaged application uses the same entry point through
``tradingbacktester.app.main``; this file exists so the app can be started from
a source checkout without installing the package.
"""

from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path

if __name__ == "__main__":
    # Must come before anything heavy is imported.  On Windows the optimiser's
    # process pool starts a child by re-running this executable with
    # --multiprocessing-fork; without freeze_support that child would re-enter
    # main() and open a second application window.
    multiprocessing.freeze_support()

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tradingbacktester.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
