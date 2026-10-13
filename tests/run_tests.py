#!/usr/bin/env python3
# Runs the Raspberry tests: every *_test.py file of this folder, one after the
# other, then install_test.sh (the real install.sh in a fake home). Nothing is
# installed and the real system is never touched: system files, commands, the
# TV, the mouse and the network are simulated.
#
# Usage, from the Raspberry_receiver/ folder:
#   python3 tests/run_tests.py            all the tests
#   python3 tests/run_tests.py selfheal   only the files whose name contains "selfheal"
#
# Needs: the websockets module (pip install "websockets>=13,<18") and, for
# install_test.sh, bash and internet access (pip installs qrcode).
import shutil
import subprocess
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
name_filter = sys.argv[1] if len(sys.argv) > 1 else ""
files = sorted(p for p in here.iterdir()
               if (p.name.endswith("_test.py") or p.name == "install_test.sh") and name_filter in p.name)

if not files:
    print(f'No test file matches "{name_filter}"')
    sys.exit(1)

results = []
for path in files:
    print(f"\n════════ {path.name} ════════", flush=True)
    # shutil.which follows PATH: on Windows, Git Bash rather than the WSL bash of System32
    command = [shutil.which("bash") or "bash", str(path)] if path.suffix == ".sh" else [sys.executable, str(path)]
    results.append((path.name, subprocess.run(command).returncode == 0))

print("\n════════ Summary ════════")
for name, ok in results:
    print(f"{'✅' if ok else '❌'} {name}")
failed_files = sum(not ok for _, ok in results)
print(f"\n{failed_files} file(s) with failures" if failed_files else "\nAll tests passed")
sys.exit(1 if failed_files else 0)
