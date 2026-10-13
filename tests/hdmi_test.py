# Tests the HDMI input used by the real tv_control.py (config.HDMI_PORT),
# with simulated cec-client commands (subprocess.run) and no waiting.
import importlib
import subprocess
import sys
import types
from pathlib import Path

REPO = str(Path(__file__).resolve().parents[1])  # Raspberry_receiver/
sys.path.insert(0, REPO)

passed = failed = 0


def check(label, condition, detail=""):
    global passed, failed
    passed, failed = passed + bool(condition), failed + (not condition)
    print(f"{'OK ' if condition else 'KO '} {label} {detail}")


def run_with_port(port):
    """Loads tv_control with config.HDMI_PORT = port and runs the accept sequence."""
    cfg = types.ModuleType("config")
    if port is not None:
        cfg.HDMI_PORT = port
    sys.modules["config"] = cfg
    commands = []
    real_run, real_sleep = subprocess.run, __import__("time").sleep
    subprocess.run = lambda cmd, shell=False: commands.append(cmd)
    __import__("time").sleep = lambda s: None
    try:
        sys.modules.pop("tv_control", None)
        tv_control = importlib.import_module("tv_control")
        threads = []
        real_thread = tv_control.threading.Thread

        def thread(target, daemon):
            t = real_thread(target=target, daemon=daemon)
            threads.append(t)
            return t

        tv_control.threading.Thread = thread
        try:
            tv_control.tv_on_and_accept()
            for t in threads:
                t.join(5)
            tv_control.tv_return()
        finally:
            tv_control.threading.Thread = real_thread
    finally:
        subprocess.run, __import__("time").sleep = real_run, real_sleep
    return commands


# Default value of the real config.py
real_config = open(REPO + "/config.py", encoding="utf-8").read()
check("config.py: HDMI_PORT = 3 by default", "\nHDMI_PORT = 3\n" in real_config)

cmds = run_with_port(3)
check("port 3: TV turned on first", cmds[0] == 'echo "on 0" | cec-client -s -d 1', cmds[:1])
check("port 3: 'as' sent 5 times on port 3",
      cmds.count('echo "as" | cec-client -s -d 1 -p 3') == 5)
check("port 3: then 'is' (switch thread) and 'is' (tv_return)",
      cmds.count('echo "is" | cec-client -s -d 1') == 2)
check("port 3: same commands as before the setting existed",
      cmds == ['echo "on 0" | cec-client -s -d 1'] + ['echo "as" | cec-client -s -d 1 -p 3'] * 5
      + ['echo "is" | cec-client -s -d 1'] * 2)

cmds = run_with_port(2)
check("port 2: 'as' sent on port 2", cmds.count('echo "as" | cec-client -s -d 1 -p 2') == 5
      and not any("-p 3" in c for c in cmds))

cmds = run_with_port("4")
check("port given as text \"4\": used as 4", cmds.count('echo "as" | cec-client -s -d 1 -p 4') == 5)

try:
    cmds = run_with_port("3; rm -rf ~")
    injected = any("rm -rf" in c for c in cmds)
except Exception:
    injected = False
check("invalid value: never inserted into the shell command", not injected)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
