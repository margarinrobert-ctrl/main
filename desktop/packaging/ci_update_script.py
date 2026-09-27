"""Write the in-app updater's own script, for the Windows build to run.

    python packaging/ci_update_script.py UPDATE_FILE APP_DIR LOG OUT_PS1

The build installs (or unpacks) a copy, runs this script's output with Windows
PowerShell exactly as the application would, and checks the result -- so the
update path is exercised on real Windows on every build.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tradingbacktester import updater  # noqa: E402


def main() -> int:
    source, app_dir, log, out = (Path(a) for a in sys.argv[1:5])
    update = updater.inspect_update(source)
    print(f"{source.name}: kind={update.kind} ok={update.ok} {update.reason}")
    if not update.ok:
        return 1
    # PID 1 is never a Windows process (Windows PIDs are multiples of 4), so
    # the script does not wait for anything.
    script = updater.build_script(update, app_dir, 1, log, relaunch=False)
    out.write_text(script, encoding="utf-8-sig")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
