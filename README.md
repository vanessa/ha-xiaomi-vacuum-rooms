# ha-xiaomi-vacuum-rooms

Room-by-room cleaning for Xiaomi MIoT robot vacuums in Home Assistant. Your voice assistant shows each script as a scene.

Clean one room, mop one room, or clean the whole house, by voice.

Tested on a **Xiaomi H50 Pro** (`xiaomi.vacuum.ov42gl`). The scripts work on any MIoT vacuum that has the `start-vacuum-room-sweep` action. See [If entities are missing](#if-entities-are-missing).

## Why this exists

The `vacuum.*` entity from `xiaomi_home` supports six commands: `START`, `STOP`, `PAUSE`, `RETURN_HOME`, `LOCATE`, and `FAN_SPEED`. It has no `send_command`. Room recipes written for `xiaomi_miio` or Roborock therefore cannot work with this integration.

`xiaomi_home` shows each MIoT action as a `notify` entity instead. Room cleaning goes through `notify.send_message` on that entity. No obvious documentation says this.

## Requirements

- Home Assistant 2024.6 or later. Earlier versions have no `NotifyEntity`.
- `xiaomi_home` from HACS, configured with your Xiaomi account.
- A saved map with named rooms in the Xiaomi Home app. Home Assistant cannot create this map.
- For voice control: Nabu Casa Cloud, or your own Alexa skill.

## Install

You do not need to clone this repository. Download the raw files, or give the whole task to an agent. See [Install with an agent](#install-with-an-agent).

1. Run the [pre-flight checks](#pre-flight). The checks are read-only.
2. Copy [`scripts.yaml`](https://raw.githubusercontent.com/vanessa/ha-xiaomi-vacuum-rooms/main/scripts.yaml) into your `scripts.yaml` file. You can also install it as a package under a `script:` key.
3. Replace the entity prefix. See [Find your entity prefix](#find-your-entity-prefix).
4. Replace the room IDs. See [Find your room IDs](#find-your-room-ids).
5. Read [The orphan trap](#the-orphan-trap). Then open Developer Tools > YAML and reload the scripts.
6. Expose the `vacuum_*`, `mop_*`, and `clean_*` scripts to your voice assistant.
7. Do not expose the two `vacuum_helper_*` scripts. They take parameters, and a scene cannot supply them.

The aliases in `scripts.yaml` are Portuguese, because that is the language of the original household. Translate each `alias:` into your language. The alias is the phrase that the assistant listens for, and nothing else depends on it. Entity IDs, field names, and comments are English.

## Install with an agent

You must read both substitution values from your own system. An agent with access to your Home Assistant container can do this for you. The agent needs a shell inside the container, a long-lived access token, or both.

The agent does not need a clone. It downloads each file from a URL.

Give the agent this text:

```
Install this on my Home Assistant. Follow the guide at
https://raw.githubusercontent.com/vanessa/ha-xiaomi-vacuum-rooms/main/AGENTS.md

Home Assistant is at http://<your-ha-host>:8123
Token: <your long-lived access token>

Run the pre-flight checks first. Show me the results before you install.
Ask me before you start the robot.
```

[`AGENTS.md`](AGENTS.md) tells the agent to do these steps:

1. Download `scripts.yaml` and `preflight.py` from their raw URLs.
2. Read your entity prefix and your room IDs from the live system.
3. Replace both values in `scripts.yaml`.
4. Install the file and reload the scripts.
5. Remove orphaned entities from an earlier install.
6. Expose the correct scripts to your voice assistant.

Two facts about agents and this package:

- Every script moves a real machine through your home. `AGENTS.md` tells the agent to ask you before it starts the robot. Put the same instruction in your own prompt.
- A fast report of success is often wrong here. The accepted cleaning configuration reverts about 2 seconds after dispatch. An agent that reads the state once at 5 seconds reports success for a job that becomes a whole-house clean. `AGENTS.md` gives the correct test. Ask the agent which results it tested on hardware.

## Pre-flight

Run these checks before you install, with an agent or without one. The checks are read-only. They find the faults that otherwise appear later as a scene that does nothing.

```bash
curl -fsSL https://raw.githubusercontent.com/vanessa/ha-xiaomi-vacuum-rooms/main/preflight.py -o preflight.py
export HA_URL=http://<your-ha-host>:8123
export HA_TOKEN=<your long-lived access token>
python3 preflight.py
```

The script makes sure that:

| Check | Why it is necessary |
|---|---|
| The API answers and the token works | The install fails at the start, not in the middle |
| Home Assistant is 2024.6 or later | Earlier versions have no `NotifyEntity`, and room cleaning is impossible |
| The entity prefix resolves | Every other entity ID comes from this prefix |
| All 10 required entities exist | A missing entity means a different MIoT spec. See [If entities are missing](#if-entities-are-missing) |
| The select options match | The most common silent fault. Read the paragraph below |
| The room list is not empty | No saved map means no rooms to address |
| The robot is docked | A warning. A paused job makes the robot clean the whole house |
| No script names collide | A warning. It shows leftovers from an earlier install |

The option test is the important one. The scripts send exact strings such as `"Vacuuming"`, `"Standard"`, and `"Level 2"`. These strings come from the translations in the MIoT spec. They differ between models and between versions of the integration. If a string does not match, `select.select_option` fails when the script runs, not when you install it.

The script prints your prefix and your room IDs when all checks pass. These are the two values that the next two sections need.

If a check fails, do not install. Correct the fault first.

## Find your entity prefix

Entity IDs from `xiaomi_home` contain your account region and your device ID:

```
vacuum.xiaomi_cn_123456789_ov42gl
       ^^^^^^ ^^ ^^^^^^^^^ ^^^^^^
       vendor region device model
```

`scripts.yaml` contains the placeholder `xiaomi_xx_000000000_ov42gl`. Pre-flight prints your real prefix. You can also read it in Developer Tools > States. Then run:

```bash
sed -i 's/xiaomi_xx_000000000_ov42gl/xiaomi_cn_123456789_ov42gl/g' scripts.yaml
```

## Find your room IDs

Pre-flight prints the room IDs. To read them yourself, open Developer Tools > States and find `sensor.<your_prefix>_room_information_p_2_16`:

```json
{"rooms": [{"id": 3, "name": "Living room"}, {"id": 4, "name": "Kitchen"}], "map_uid": 1}
```

Each map has its own IDs. A new map of your home can change the numbers.

## Common mistakes

### The two enums

These are two different properties. Most faults start here:

```
sweep_mop_type (piid 2.4)   1 Vacuuming · 2 Mopping · 3 Vacuuming & Mopping · 4 Vacuuming before mopping
sweep_type     (piid 2.5)   1 Whole-house · 2 Zone · 3 Area · 4 Edge · ...
```

`clean_mode` in `current_cleaning_config` is `sweep_type`. It is not `sweep_mop_type`. Therefore `{"rooms":[4],"clean_mode":3}` means "an Area job on room 4". It says nothing about vacuum or mop. If you read it as "mode 3 is vacuum and mop", you look for a fault that does not exist.

### Room ID encoding

The `start-vacuum-room-sweep` action (siid 2, aiid 16) takes one string parameter. The parameter is `vacuum-room-ids` (piid 15). Write the IDs with commas between them:

```yaml
- action: notify.send_message
  target:
    entity_id: notify.<prefix>_start_vacuum_room_sweep_a_2_16
  data:
    message: "{{ rooms | join(',') }}"     # -> "4,7"
```

A plain `[3,4]` in `message` fails. `notify.send_message` parses the field as YAML first, so the value arrives as a list. The spec accepts one parameter, and a list fails validation. JSON forms need inner quotes: `message: "'{{ rooms | tojson }}'"`.

The `get-room-configs` action is not a test for the format. It returns HTTP 200 for any string, and garbage strings included. Only a real clean shows the correct format.

### The paused-job trap

If an earlier job is still paused, the robot discards your room selection. It then cleans the whole house. These log lines show it:

```
18:20:00  CFG {"rooms":[7],"clean_mode":3}   accepted
18:20:02  CFG {"clean_mode":1}                2s later: whole-house instead
```

The room command was correct both times. Each script in this package therefore presses `stop_working` and waits 4 seconds when the robot is not `docked`. This guard is tested on hardware. A paused job no longer causes a whole-house clean.

The accepted configuration is also short-lived. A read a few seconds after dispatch can show a room selection that the robot discards next. Judge the result by the rooms that the robot cleans.

### The orphan trap

`script.reload` does not remove scripts that you erased from the YAML file. The entities stay in the entity registry. They stay exposed to your voice assistant, and they still run their old definitions. A voice command can therefore run a definition that exists in no file.

After you rename a script, compare the entities against your YAML file. Remove each entity that the file no longer defines. Open Settings > Devices & Services > Entities and filter by `script.`.

## Alexa

Home Assistant maps a `script` entity to the Alexa `SceneController`. The phrase is therefore "turn on \<alias\>". With the Portuguese aliases in this package:

> "Alexa, ligar Aspirar Cozinha"

Keep the two `vacuum_helper_*` scripts unexposed.

## If entities are missing

The entity suffixes `_a_2_16` and `_p_2_4` are MIoT `siid`, `piid`, and `aiid` coordinates. Each vacuum model has its own numbers. Download the spec for your model:

```
https://miot-spec.org/miot-spec-v2/instance?type=<urn of the model>
```

Then map these six items: `start-vacuum-room-sweep`, `stop-working`, `sweep-mop-type`, `mode`, `mop-water-output-level`, and `room-information`. Update `scripts.yaml` and the `REQUIRED` table in `preflight.py`.

## Test status

This table gives the true test status of each behavior:

| Behavior | Status |
|---|---|
| Single-room vacuum through `start-vacuum-room-sweep` | Tested on hardware |
| `clean_mode` is `sweep_type`, not `sweep_mop_type` | Tested on hardware |
| A paused job causes a whole-house clean | Tested. Reproduced from the logs |
| Orphaned scripts survive `script.reload` | Tested. 19 orphans found |
| The 4-second reset guard stops the whole-house fallback | Tested on hardware |
| Multi-room selection (`"4,7"`) | Not tested. An earlier result was a short-lived state, read before it reverted |

## License

MIT. See `LICENSE`.
