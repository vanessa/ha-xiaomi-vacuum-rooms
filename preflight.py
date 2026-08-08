#!/usr/bin/env python3
"""
Pre-flight checks for ha-xiaomi-vacuum-rooms.

Read-only. Talks to the Home Assistant REST API and verifies that every entity
and every option string the scripts depend on actually exists on this system,
BEFORE anything is written. Run it, get a clean bill, then install.

    export HA_URL=http://homeassistant.local:8123
    export HA_TOKEN=<long-lived access token>
    python3 preflight.py --prefix xiaomi_cn_123456789_ov42gl

Omit --prefix and it will try to discover it.

Exit codes:  0 = all checks passed   1 = a blocking failure   2 = usage error
"""
import argparse, json, os, sys, urllib.request, urllib.error

FAIL, WARN, OK = [], [], []


def api(path):
    url = f"{HA_URL.rstrip('/')}/api/{path.lstrip('/')}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def check(cond, ok_msg, fail_msg, blocking=True):
    if cond:
        OK.append(ok_msg)
    else:
        (FAIL if blocking else WARN).append(fail_msg)
    return cond


# Entities the scripts reference. Suffixes are MIoT siid/piid/aiid coordinates
# and are model-specific -- a miss here means the target model's spec differs.
REQUIRED = [
    ("vacuum.{p}",                              "vacuum entity"),
    ("notify.{p}_start_vacuum_room_sweep_a_2_16", "room sweep action"),
    ("button.{p}_stop_working_a_2_51",          "stop/end job"),
    ("select.{p}_sweep_mop_type_p_2_4",         "vacuum vs mop"),
    ("select.{p}_mode_p_2_9",                   "suction"),
    ("select.{p}_mop_water_output_level_p_2_10","water level"),
    ("sensor.{p}_room_information_p_2_16",      "room list"),
    ("button.{p}_start_only_sweep_a_2_4",       "whole-house vacuum"),
    ("button.{p}_start_mop_a_2_5",              "whole-house mop"),
    ("button.{p}_start_sweep_mop_a_2_6",        "whole-house vacuum+mop"),
]

# Option strings the scripts pass to select.select_option. These come from the
# MIoT spec's translations and DO vary between models and integration versions.
# A mismatch is the most likely silent breakage, so check it explicitly.
REQUIRED_OPTIONS = {
    "select.{p}_sweep_mop_type_p_2_4":          ["Vacuuming", "Mopping"],
    "select.{p}_mode_p_2_9":                    ["Standard"],
    "select.{p}_mop_water_output_level_p_2_10": ["Level 2"],
}

SCRIPT_IDS = [
    "vacuum_helper_clean_rooms", "vacuum_helper_probe_room_id",
    "vacuum_living_room", "mop_living_room", "vacuum_kitchen", "mop_kitchen",
    "vacuum_bedroom", "mop_bedroom", "vacuum_office", "mop_office",
    "vacuum_bathroom", "mop_bathroom", "vacuum_whole_house", "mop_whole_house",
    "clean_whole_house", "robot_go_home",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", help="e.g. xiaomi_cn_123456789_ov42gl")
    args = ap.parse_args()

    # --- 1. API reachable and token valid -----------------------------------
    try:
        api("")
        OK.append("API reachable, token valid")
    except urllib.error.HTTPError as e:
        print(f"FAIL: API returned HTTP {e.code}. "
              f"{'Token rejected.' if e.code == 401 else ''}")
        return 1
    except Exception as e:
        print(f"FAIL: cannot reach {HA_URL} -- {e}")
        return 1

    # --- 2. HA version (NotifyEntity landed in 2024.6) ----------------------
    try:
        ver = api("config").get("version", "0.0")
        maj, min_ = (int(x) for x in ver.split(".")[:2])
        check((maj, min_) >= (2024, 6), f"HA {ver} supports NotifyEntity",
              f"HA {ver} is older than 2024.6 -- notify.send_message unavailable")
    except Exception as e:
        WARN.append(f"could not parse HA version ({e})")

    states = {s["entity_id"]: s for s in api("states")}

    # --- 3. Prefix -----------------------------------------------------------
    prefix = args.prefix
    if not prefix:
        cands = [e[len("vacuum."):] for e in states if e.startswith("vacuum.xiaomi_")]
        if len(cands) == 1:
            prefix = cands[0]
            OK.append(f"discovered prefix: {prefix}")
        elif not cands:
            print("FAIL: no vacuum.xiaomi_* entity. Is xiaomi_home configured?")
            return 1
        else:
            print(f"FAIL: multiple vacuums found, pass --prefix. Candidates: {cands}")
            return 1
    else:
        check(f"vacuum.{prefix}" in states, f"prefix {prefix} resolves",
              f"no entity vacuum.{prefix} -- check the prefix")

    # --- 4. Required entities ------------------------------------------------
    for tmpl, label in REQUIRED:
        eid = tmpl.format(p=prefix)
        check(eid in states, f"{label}: {eid}",
              f"MISSING {label}: {eid} -- model spec likely differs")

    # --- 5. Select options match what the scripts send -----------------------
    for tmpl, needed in REQUIRED_OPTIONS.items():
        eid = tmpl.format(p=prefix)
        if eid not in states:
            continue
        opts = states[eid]["attributes"].get("options", [])
        for want in needed:
            check(want in opts, f"{eid} offers '{want}'",
                  f"{eid} has no option '{want}' -- available: {opts}. "
                  f"Edit the option strings in scripts.yaml to match.")

    # --- 6. Rooms ------------------------------------------------------------
    room_eid = f"sensor.{prefix}_room_information_p_2_16"
    if room_eid in states:
        try:
            rooms = json.loads(states[room_eid]["state"]).get("rooms", [])
            if check(bool(rooms), f"{len(rooms)} rooms on the saved map",
                     "room list is EMPTY -- create and name rooms in the "
                     "Xiaomi Home app first; HA cannot fix this"):
                print("\nRoom IDs to put in scripts.yaml:")
                for r in rooms:
                    print(f"    id {r.get('id')} = {r.get('name')}")
        except (ValueError, TypeError):
            FAIL.append(f"{room_eid} state is not JSON: {states[room_eid]['state'][:80]}")

    # --- 7. Robot should be docked before installing -------------------------
    vac = states.get(f"vacuum.{prefix}", {}).get("state")
    check(vac == "docked", "robot is docked",
          f"robot state is '{vac}', not 'docked'. A paused or running job makes "
          f"room selection revert to a whole-house clean -- dock it first.",
          blocking=False)

    # --- 8. Name collisions with existing scripts ----------------------------
    clashes = [s for s in SCRIPT_IDS if f"script.{s}" in states]
    check(not clashes, "no script name collisions",
          f"these script entities already exist and will be overwritten: {clashes}. "
          f"If they are from an older install, remove the orphans after reload.",
          blocking=False)

    # --- Report --------------------------------------------------------------
    print()
    for m in OK:   print(f"  ok    {m}")
    for m in WARN: print(f"  warn  {m}")
    for m in FAIL: print(f"  FAIL  {m}")
    print(f"\n{len(OK)} passed, {len(WARN)} warnings, {len(FAIL)} failures")
    if FAIL:
        print("\nDo not install until the failures above are resolved.")
        return 1
    print(f"\nPre-flight passed. Prefix to substitute: {prefix}")
    return 0


if __name__ == "__main__":
    HA_URL = os.environ.get("HA_URL", "")
    HA_TOKEN = os.environ.get("HA_TOKEN", "")
    if not HA_URL or not HA_TOKEN:
        print("Set HA_URL and HA_TOKEN environment variables.", file=sys.stderr)
        sys.exit(2)
    sys.exit(main())
