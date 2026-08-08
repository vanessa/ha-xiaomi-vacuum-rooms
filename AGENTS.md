# Agent install guide

This guide tells an AI agent how to install this package on a live Home Assistant system.

The guide assumes that you have no clone and no local copy. You download each file from a URL.

A person can also follow these steps. The text is written for an agent that has real access to the Home Assistant container.

Read this guide to the end before you change anything. The discovery steps and the pre-flight step are necessary. This package needs values from the target system, and it fails without a message if those values are wrong.

## Source files

| File | URL |
|---|---|
| Repository | <https://github.com/vanessa/ha-xiaomi-vacuum-rooms> |
| `scripts.yaml` | <https://raw.githubusercontent.com/vanessa/ha-xiaomi-vacuum-rooms/main/scripts.yaml> |
| `preflight.py` | <https://raw.githubusercontent.com/vanessa/ha-xiaomi-vacuum-rooms/main/preflight.py> |
| This guide | <https://raw.githubusercontent.com/vanessa/ha-xiaomi-vacuum-rooms/main/AGENTS.md> |

Download `scripts.yaml` and read it before you install it. You write this file into the home of a person, therefore you must know its contents:

```bash
curl -fsSL https://raw.githubusercontent.com/vanessa/ha-xiaomi-vacuum-rooms/main/scripts.yaml -o /tmp/scripts.yaml
wc -l /tmp/scripts.yaml && cat /tmp/scripts.yaml
```

If you have a web-fetch tool and no shell, get the same raw URL with that tool. If you have neither, stop and tell the user. Do not write the file from memory. It contains exact MIoT entity IDs, and you cannot guess them.

You do not need `git clone`. No step needs the repository on disk.

## Access

You need one of these, and both are better:

- A shell inside the Home Assistant container. The configuration directory is `/config`, or `/homeassistant` on some installs. A shell gives you file writes and log access.
- A long-lived access token for the REST API and the WebSocket API. The user creates one in the user profile, under Security.

## Rules

1. CAUTION: Ask the user before you start the robot. Every script moves a physical machine through the home of a person. Name the room before you send the robot to it.
2. Back up the file before you write to it: `cp /config/scripts.yaml /config/scripts.yaml.bak-$(date +%Y%m%d)`.
3. Do not invent entity IDs. Read them from the system. An ID that looks correct but is wrong does nothing, and it reports no error.
4. Do not report a step as tested from one state read. Read [Test the result](#test-the-result) first.
5. Do not print or commit tokens, `secrets.yaml`, or the contents of `.storage/`.

## Step 1: Run the pre-flight checks

Run this step before you write anything. The script is read-only. It makes sure that every entity and every option string exists on this system.

```bash
curl -fsSL https://raw.githubusercontent.com/vanessa/ha-xiaomi-vacuum-rooms/main/preflight.py -o /tmp/preflight.py
export HA_URL=http://<ha-host>:8123
export HA_TOKEN=<long-lived access token>
python3 /tmp/preflight.py
```

If the script cannot find the prefix, add `--prefix <prefix>`.

The script makes sure that:

| Check | Why it is necessary |
|---|---|
| The API answers and the token works | The run fails at the start, not in the middle |
| Home Assistant is 2024.6 or later | Earlier versions have no `NotifyEntity`, and room cleaning is impossible |
| The entity prefix resolves | Every other entity ID comes from this prefix |
| All 10 required entities exist | A missing entity means a different MIoT spec. See [If entities are missing](#if-entities-are-missing) |
| The select options match | The most common silent fault. Read the paragraph below |
| The room list is not empty | No saved map means no rooms to address, and Home Assistant cannot create the map |
| The robot is docked | A warning. A paused job makes the robot clean the whole house |
| No script names collide | A warning. It shows leftovers from an earlier install |

The option test is the important one. The scripts send the exact strings `"Vacuuming"`, `"Standard"`, and `"Level 2"`. These strings come from the translations in the MIoT spec. They differ between models and between versions of the integration. A string that does not match makes `select.select_option` fail at run time, not at install time.

The script prints the prefix and the room IDs when all checks pass.

If a check fails, stop. Report the failure to the user. Do not work around it.

## Step 2: Replace the two values

Pre-flight gives you both values.

**The entity prefix.** `scripts.yaml` contains the placeholder `xiaomi_xx_000000000_ov42gl`:

```bash
sed -i "s/xiaomi_xx_000000000_ov42gl/<prefix from pre-flight>/g" /tmp/scripts.yaml
```

**The room IDs.** The scripts use example IDs: 3 for the living room, 4 for the kitchen, 5 for the bedroom, 6 for the office, and 7 for the bathroom. These numbers are not the same on every map. Change each `rooms:` list to the IDs from pre-flight. Remove the scripts for rooms that do not exist, and add scripts for rooms that do. A script with an unknown room ID gives no error. It cleans nothing.

**The aliases.** Translate each `alias:` into the language that the household speaks to the voice assistant. The aliases in the file are Portuguese. The alias is the phrase that the assistant listens for. Keep entity IDs, field names, and comments in English.

Then make sure that the file still parses:

```bash
python3 -c "import yaml;d=yaml.safe_load(open('/tmp/scripts.yaml'));print(len(d),'scripts OK')"
```

## Step 3: Install the file and reload

Back up `/config/scripts.yaml` first. Then append the new content, or install it as a package under a `script:` key. Then reload:

```bash
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" $HA_URL/api/services/script/reload
```

Then make sure that the new scripts exist, and read the log for YAML errors:

```bash
curl -s -H "Authorization: Bearer $HA_TOKEN" $HA_URL/api/states \
  | python3 -c "import json,sys;print([e['entity_id'] for e in json.load(sys.stdin) if e['entity_id'].startswith('script.')])"
```

## Step 4: Remove orphaned entities

`script.reload` does not remove scripts that you erased from the YAML file. The entities stay in the entity registry. They stay exposed to the voice assistant, and they still run their old definitions. A voice command can therefore run a definition that exists in no file. Pre-flight warns about name collisions, and this step removes them.

Compare the `script.` entities against the scripts in your YAML file. Remove each entity that the file no longer defines. Use the WebSocket API command `config/entity_registry/remove`. A person can also remove them in Settings > Devices & Services > Entities.

## Step 5: Expose the scripts

Expose the `vacuum_*`, `mop_*`, and `clean_*` scripts, and `robot_go_home`.

Do not expose the two `vacuum_helper_*` scripts. They take parameters, and a scene cannot supply them.

Use the WebSocket command `homeassistant/expose_entity` with `assistants: ["cloud.alexa"]` and `should_expose: true`. Then make sure that the new entities are exposed. Do not assume that a default setting exposed them.

Home Assistant maps a script to the Alexa `SceneController`. The phrase is therefore "turn on \<alias\>".

## Test the result

An agent reports a false success most often at this step.

The accepted cleaning configuration is short-lived. A read of `current_cleaning_config` a few seconds after dispatch can show a room selection that the robot discards next. An agent made this exact mistake during development and reported the result as tested. These are the log lines:

```
18:20:00  CFG {"rooms":[7],"clean_mode":3}   accepted
18:20:02  CFG {"clean_mode":1}                2s later: whole-house instead
```

The cause is a paused job. If an earlier job is still paused, the robot discards the room selection and cleans the whole house. Each script guards against this. It presses `stop_working` and waits 4 seconds when the robot is not docked.

To test one room clean:

1. Make sure that the robot is `docked`.
2. Ask the user for permission. This step moves the robot.
3. Start the clean. Then read `current_cleaning_config` for 15 seconds or more.
4. Make sure that `clean_mode` did not revert to `1`.
5. Judge the result by the rooms that the robot cleans. A state read alone is not proof.

Two more facts:

- `clean_mode` in `current_cleaning_config` is `sweep_type`. It is the job shape: whole-house, zone, or area. It is not `sweep_mop_type`. Do not report "mode 3 is vacuum and mop".
- `get-room-configs` returns HTTP 200 for any string, and garbage strings included. It cannot validate a room ID format. Only a real clean can.

## If entities are missing

The entity suffixes `_a_2_16` and `_p_2_4` are MIoT `siid`, `piid`, and `aiid` coordinates. Each vacuum model has its own numbers. Download the spec for the model:

```
https://miot-spec.org/miot-spec-v2/instance?type=<urn of the model>
```

Then map these six items: `start-vacuum-room-sweep`, `stop-working`, `sweep-mop-type`, `mode`, `mop-water-output-level`, and `room-information`. Update `scripts.yaml` and the `REQUIRED` table in `preflight.py`.

## Your report to the user

Name the behaviors that you tested on hardware. Name the behaviors that you did not test. One result is usually still open: multi-room selection (`"4,7"`). State this, and do not imply a wider test than you did.

The 4-second reset guard is tested. A paused job no longer causes a whole-house clean.
