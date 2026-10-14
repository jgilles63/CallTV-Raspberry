# Self-repair of the Raspberry (selfheal.py): Wi-Fi lost, server or box down,
# TV page or agent not connected, nightly restart, never during a call,
# at most one restart per hour. Time, network and agent state are simulated.
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Raspberry_receiver/
import selfheal as h  # noqa: E402

passed = failed = 0


def check(label, condition, detail=""):
    global passed, failed
    passed, failed = passed + bool(condition), failed + (not condition)
    print(f"{'OK ' if condition else 'KO '} {label} {detail}")


tmp = tempfile.mkdtemp()
APP = os.path.join(tmp, "AppelerMamie")
os.makedirs(APP)
h.STATE_FILE = os.path.join(tmp, "var", "selfheal.json")

world = {}
actions = []


def reset(**changes):
    world.clear()
    world.update(t=1_000_000.0, uptime=5 * 3600.0, boot="boot-1", hour=14,
                 server=True, internet=True, gateway=True, agent={"registered": True, "rejected": False,
                                                                   "inCall": False, "displayConnected": True})
    world.update(changes)
    actions.clear()
    write_config('SERVER_URL = "wss://appelermami.fr"\nNIGHTLY_REBOOT_HOUR = 4\n')


def write_config(text):
    with open(os.path.join(APP, "config.py"), "w", encoding="utf-8") as f:
        f.write(text)


def write_agent():
    path = os.path.join(APP, "agent_state.json")
    if world["agent"] is None:
        if os.path.exists(path):
            os.remove(path)
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dict(world["agent"], time=world.get("agentTime", world["t"])), f)


def can_connect(host, port, timeout=5):
    if host == "appelermami.fr":
        return world["server"]
    return world["internet"]


h.can_connect = can_connect
h.gateway_answers = lambda: world["gateway"]
h.uptime = lambda: world["uptime"]
h.boot_id = lambda: world["boot"]
h.now = lambda: world["t"]
h.local_hour = lambda: world["hour"]
h.act = lambda command: actions.append(" ".join(command))


def minutes(n, state):
    """n passes, one per minute (the time and the uptime move on). Returns the actions."""
    done = []
    for _ in range(n):
        write_agent()
        action = h.check_once(APP, state)
        if action:
            done.append(action)
        world["t"] += 60
        world["uptime"] += 60
        if not world.get("agentFrozen"):
            world["agentTime"] = world["t"]
    return done


# ------------------------------------------------------------------
reset()
state = {}
check("all fine: nothing done for 30 min", minutes(30, state) == [] and actions == [])
check("network state kept: ok", state["network"] == "ok")

reset(server=False, internet=True)
state = {}
check("only our server down (Internet works): nothing done, ever", minutes(60, state) == [] and state["network"] == "server")

reset(server=False, internet=False, gateway=True)
state = {}
check("box without Internet (the box answers): nothing done", minutes(60, state) == [] and state["network"] == "internet")

# ------------------------------------------------------------------
reset(server=False, internet=False, gateway=False)
state = {}
done = minutes(5, state)
check("Wi-Fi lost: nothing during the first 5 min", done == [])
done = minutes(1, state)
check("Wi-Fi lost 5 min: network restarted", done == ["network"] and actions == ["systemctl restart NetworkManager"])
done = minutes(4, state)
check("... not again before 5 more min", done == [])
done = minutes(1, state)
check("... restarted again after 5 min", done == ["network"])
done = minutes(5, state)
check("Wi-Fi lost 15 min: Raspberry restarted", done[-1:] == ["reboot"] and actions[-1] == "systemctl reboot", str(done))
check("reboot recorded in the history", state["history"][-1]["action"] == "reboot" and state["history"][-1]["reason"] == "wifi")
saved = json.load(open(h.STATE_FILE))
check("state saved before restarting (survives the restart)", saved["last_reboot"] == state["last_reboot"])

# after the restart: new boot, Wi-Fi still lost
world["boot"] = "boot-2"
world["uptime"] = 120.0
state = h.load_state()
actions.clear()
done = minutes(55, state)
check("after the restart, still lost: no second restart within the hour", "reboot" not in done, str(done))
check("... the network is still restarted every 5 min", done.count("network") >= 9)
done = minutes(10, state)
check("... restart again once the hour has passed", "reboot" in done)

reset(server=False, internet=False, gateway=False, uptime=120.0)
state = {"bootId": "boot-1", "networkDownSince": world["t"] - 20 * 60}
done = minutes(8, state)
check("no restart in the first 10 min after startup", "reboot" not in done, str(done))
check("... then it is allowed", "reboot" in minutes(3, state))

reset(server=False, internet=False, gateway=False)
state = {}
minutes(3, state)
world.update(server=True, internet=True, gateway=True)
done = minutes(10, state)
check("Wi-Fi back after 3 min: nothing done, problem forgotten", done == [] and "networkDownSince" not in state)

# ------------------------------------------------------------------
reset(server=False, internet=False, gateway=False)
world["agent"]["inCall"] = True
state = {}
check("during a call: nothing at all, even after 30 min", minutes(30, state) == [] and actions == [])
world["agent"]["inCall"] = False
done = minutes(1, state)
check("call over, Wi-Fi still lost for long: repaired at once", done == ["reboot"], str(done))

reset(server=False, internet=False, gateway=False)
world["agent"]["inCall"] = True
world["agentTime"] = world["t"] - 600
world["agentFrozen"] = True
state = {}
check("agent state too old (agent stuck): not trusted as 'in call'", "network" in minutes(6, state))

# ------------------------------------------------------------------
reset()
world["agent"]["displayConnected"] = False
state = {}
done = minutes(3, state)
check("TV page not connected: nothing during 3 min", done == [])
done = minutes(1, state)
check("TV page not connected 3 min: Chromium restarted",
      done == ["page"] and actions == ["systemctl restart chromium-autolaunch.service"])
done = minutes(9, state)
check("... not again within 10 min", done == [])
done = minutes(3, state)
check("... page still not connected after 15 min: Raspberry restarted", "reboot" in done, str(done))

reset()
world["agent"]["displayConnected"] = None
state = {}
check("server of an older version (page state unknown): nothing done", minutes(30, state) == [])

reset()
world["agent"]["displayConnected"] = False
world["agent"]["inCall"] = True
state = {}
check("page not connected during a call: Chromium not restarted", minutes(10, state) == [])

# TV page stuck during a call (told by the server to the agent: displayStuckAt)
reset()
world["agent"]["displayStuckAt"] = world["t"] - 30
state = {}
done = minutes(1, state)
check("page stuck during a call: Chromium restarted at once",
      done == ["page"] and actions == ["systemctl restart chromium-autolaunch.service"])
check("... reason in the history", state["history"][-1]["reason"] == "page stuck during a call")
check("... same stuck page: not restarted again", minutes(30, state) == [])
world["agent"]["displayStuckAt"] = world["t"]
done = minutes(10, state)
check("stuck again later: restarted again (at most every 10 min)", done == ["page"], str(done))

reset()
world["agent"].update(displayStuckAt=world["t"] - 30, inCall=True)
state = {}
check("page stuck but a call in progress: wait", minutes(5, state) == [])
world["agent"]["inCall"] = False
check("... restarted once the call is over", minutes(1, state) == ["page"])

reset()
world["agent"]["displayStuckAt"] = None
state = {}
check("never stuck (or agent of an older version): nothing done", minutes(30, state) == [])

reset()
world["agent"]["displayStuckAt"] = "yesterday"
state = {}
check("unexpected value: ignored", minutes(5, state) == [])

# ------------------------------------------------------------------
reset()
world["agent"].update(registered=False)
state = {}
done = minutes(10, state)
check("agent not connected (server reachable): nothing during 10 min", done == [])
done = minutes(1, state)
check("agent not connected 10 min: agent restarted",
      done == ["agent"] and actions == ["systemctl restart tv-control.service"])

reset()
world["agent"].update(registered=False, rejected=True)
state = {}
check("agent refused by the server (not authorized): left alone", minutes(30, state) == [])

reset(agent=None)
state = {}
check("no agent state at all (agent stopped): agent restarted after 10 min", "agent" in minutes(12, state))

reset(server=False, internet=True)
world["agent"].update(registered=False)
state = {}
check("agent not connected because the server is down: left alone", minutes(30, state) == [])

# ------------------------------------------------------------------
reset(hour=4)
state = {}
done = minutes(1, state)
check("4 h, on for 5 h: nightly restart", done == ["reboot"] and state["history"][-1]["reason"] == "nightly")
world["boot"] = "boot-2"
world["uptime"] = 120.0
check("after the nightly restart, same hour: not again", minutes(58, state) == [])

reset(hour=4, uptime=2 * 3600.0)
state = {}
check("4 h but restarted 2 h ago (e.g. power cut): no nightly restart", minutes(1, state) == [])

reset(hour=4)
world["agent"]["inCall"] = True
state = {}
check("4 h during a call: no restart", minutes(1, state) == [])
world["agent"]["inCall"] = False
check("... done right after the call", minutes(1, state) == ["reboot"])

reset(hour=3)
state = {}
check("other hour: no nightly restart", minutes(1, state) == [])

reset(hour=2)
write_config('SERVER_URL = "wss://appelermami.fr:8443"\nNIGHTLY_REBOOT_HOUR = 2\n')
state = {}
check("NIGHTLY_REBOOT_HOUR = 2 in config.py: restart at 2 h", minutes(1, state) == ["reboot"])

reset(hour=4)
write_config('SERVER_URL = "wss://appelermami.fr"\nNIGHTLY_REBOOT_HOUR = None\n')
state = {}
check("NIGHTLY_REBOOT_HOUR = None: never", minutes(1, state) == [])

check("settings read: server, port, hour",
      (write_config('SERVER_URL = "wss://example.org:8443"\nNIGHTLY_REBOOT_HOUR = 5\n'), h.read_settings(APP))[1]
      == ("wss://example.org:8443", 5))
check("settings: old config.py without the hour: 4 h", (write_config('SERVER_URL = "wss://x.fr"\n'), h.read_settings(APP))[1] == ("wss://x.fr", 4))

# ------------------------------------------------------------------
reset(server=False, internet=False, gateway=False)
state = {}
for _ in range(40):
    minutes(60, state)
check("history limited to the last 20 actions", len(state["history"]) == 20)
saved_mode = oct(os.stat(h.STATE_FILE).st_mode & 0o777)
check("state file written", os.path.exists(h.STATE_FILE), saved_mode)

h.save_state({"history": [1]})
with open(h.STATE_FILE, "w") as f:
    f.write("{broken")
check("broken state file: started again from scratch", h.load_state() == {})

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
