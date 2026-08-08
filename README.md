# ha-xiaomi-vacuum-rooms

Room-addressable cleaning for Xiaomi MIoT robot vacuums in Home Assistant, exposed to Alexa as scenes.

Drop-in `scripts.yaml` for Xiaomi vacuums running under the [`xiaomi_home`](https://github.com/XiaomiHome/ha_xiaomi_home) integration: clean one named room, mop one named room, or run the whole house, by voice.

Developed against a **Xiaomi H50 Pro** (`xiaomi.vacuum.ov42gl`). Should work on any MIoT vacuum whose spec exposes the `start-vacuum-room-sweep` action — see [Porting to another model](#porting-to-another-model).

## Why this exists

`xiaomi_home`'s `vacuum.*` entity implements only `START`, `STOP`, `PAUSE`, `RETURN_HOME`, `LOCATE` and `FAN_SPEED`. **There is no `send_command`.** Every room-cleaning recipe written for `xiaomi_miio` or Roborock is therefore inapplicable — `vacuum.send_command` simply does not exist on these entities.

`xiaomi_home` instead surfaces each MIoT *action* as a **`notify` entity**. Room cleaning goes through `notify.send_message`, which is not obvious and not documented anywhere prominent.

## Requirements

- Home Assistant ≥ 2024.6 (needs `NotifyEntity`)
- `xiaomi_home` installed via HACS and configured with your Xiaomi account
- A **saved map with named rooms** in the Xiaomi Home app — rooms must exist before HA can address them
- For voice: Nabu Casa Cloud, or a self-hosted Alexa skill

## Install

1. Copy the contents of `scripts.yaml` into your `scripts.yaml` (or a package under `packages/`, nested beneath a `script:` key).
2. Substitute your entity prefix — see [Finding your entity prefix](#finding-your-entity-prefix).
3. Substitute your room IDs — see [Finding your room IDs](#finding-your-room-ids).
4. Developer Tools → YAML → **Reload scripts**. See [the orphan trap](#the-orphan-trap) first.
5. Expose the `vacuum_*` / `mop_*` / `clean_*` scripts to your voice assistant. **Do not expose the two `vacuum_helper_*` scripts.**

The script aliases in this repo are **Portuguese**, because that is the language spoken to Alexa in the original setup. Entity IDs, fields and comments are English. Translate the `alias:` values to whatever you speak — that string is what the assistant listens for, and nothing else depends on it.

## Installing with an agent

Both substitutions above have to be read off your own system, which makes this
a good fit for an AI coding agent that has access to your Home Assistant
container — a shell inside it, a long-lived access token, or both.

[`AGENTS.md`](AGENTS.md) is written for exactly that: point the agent at it and
it will discover your entity prefix and room IDs, substitute them, install and
reload the scripts, clean up orphaned entities from any previous install, and
expose the right scripts to your voice assistant.

```
Read AGENTS.md in this repo and install this package on my Home Assistant.
You have <shell access to the HA container / a long-lived token at ...>.
Ask me before starting the robot.
```

Two things worth knowing before you hand this to an agent:

- **Insist on consent before dispatch.** Every script moves a real machine
  around your home. `AGENTS.md` instructs the agent not to start the robot
  without asking; keep that instruction in your prompt too.
- **Distrust a quick "verified".** This system has a specific trap where the
  accepted cleaning config reverts about two seconds after dispatch, so an
  agent polling once at +5 s will report success on a run that is about to
  become a whole-house clean. `AGENTS.md` documents the correct check, but it
  is worth asking the agent which claims it confirmed on hardware and which it
  inferred.

## Finding your entity prefix

Entity IDs from `xiaomi_home` encode your account region and device id:

```
vacuum.xiaomi_cn_123456789_ov42gl
       ^^^^^^ ^^ ^^^^^^^^^ ^^^^^^
       vendor region device model
```

This repo ships the placeholder `xiaomi_xx_000000000_ov42gl`. Find yours under Developer Tools → States, then:

```bash
sed -i 's/xiaomi_xx_000000000_ov42gl/xiaomi_cn_123456789_ov42gl/g' scripts.yaml
```

## Finding your room IDs

Developer Tools → States → `sensor.<your_prefix>_room_information_p_2_16`:

```json
{"rooms": [{"id": 3, "name": "Living room"}, {"id": 4, "name": "Kitchen"}], "map_uid": 1}
```

IDs are per-map. Re-mapping your home can renumber them.

## The parts that are easy to get wrong

### The two enums

These are distinct properties, and confusing them is the single most common failure:

```
sweep_mop_type (piid 2.4)   1 Vacuuming · 2 Mopping · 3 Vacuuming & Mopping · 4 Vacuuming before mopping
sweep_type     (piid 2.5)   1 Whole-house · 2 Zone · 3 Area · 4 Edge · ...
```

**`clean_mode` in `current_cleaning_config` is `sweep_type`, not `sweep_mop_type`.** So `{"rooms":[4],"clean_mode":3}` means *"an Area job covering room 4"* — it says nothing about whether the robot vacuums or mops. Reading it as "mode 3 = vacuum and mop" will send you chasing a bug that isn't there.

### Room ID encoding

`start-vacuum-room-sweep` (siid 2 / aiid 16) takes **one** string parameter, `vacuum-room-ids` (piid 15), as comma-separated IDs:

```yaml
- action: notify.send_message
  target:
    entity_id: notify.<prefix>_start_vacuum_room_sweep_a_2_16
  data:
    message: "{{ rooms | join(',') }}"     # -> "4,7"
```

A bare `[3,4]` in `message` does not work: `notify.send_message` YAML-parses the field first, so it arrives as a list and fails validation against the single-parameter spec. JSON forms need inner quoting — `message: "'{{ rooms | tojson }}'"`.

**`get-room-configs` is not a usable probe.** It returns HTTP 200 for any string, including garbage. Only a real run confirms the format.

### The paused-job trap

**If a previous job is still paused, the robot discards the room selection and starts a whole-house clean instead.** Observed directly:

```
18:17:29  CFG {"rooms":[5],"clean_mode":3}   bedroom job accepted
18:17:42  STATE paused                        job left paused
18:20:00  CFG {"rooms":[7],"clean_mode":3}   bathroom job accepted
18:20:02  CFG {"clean_mode":1}                2s later: reverted to whole-house
```

The room command was correct both times. Every script here therefore presses `stop_working` and waits 4 s when the robot is not `docked`, before issuing the command.

A corollary for anyone debugging this: **the accepted config is transient.** Reading `current_cleaning_config` a few seconds after dispatch can show a room selection that is about to be discarded. Confirm against what the robot actually cleans, not against a state read.

### The orphan trap

**`script.reload` does not delete scripts you removed from YAML.** They survive in the entity registry, stay exposed to your voice assistant, and keep firing — so a renamed scene can silently keep running its old definition. Renaming scripts leaves orphans behind that must be removed from the entity registry by hand (Settings → Devices & Services → Entities, filter by `script.`).

## Alexa

Home Assistant maps a `script` entity to Alexa's `SceneController`, so the phrasing is *"Alexa, turn on \<alias\>"* — not "Alexa, ask ... to ...". With Portuguese aliases:

> "Alexa, ligar Aspirar Cozinha"

Keep the `vacuum_helper_*` scripts unexposed; they take parameters and are meaningless as scenes.

## Porting to another model

`scripts.yaml` hardcodes entity IDs whose suffixes are MIoT `siid`/`piid`/`aiid` coordinates (`_a_2_16`, `_p_2_4`). These are **spec-specific and will differ on other models.** To port, pull your model's spec:

```
https://miot-spec.org/miot-spec-v2/instance?type=<your urn>
```

and map: `start-vacuum-room-sweep`, `stop-working`, `sweep-mop-type`, `mode`, `mop-water-output-level`, `room-information`.

## Verification status

Honest accounting of what has and has not been proven on real hardware:

| Behaviour | Status |
|---|---|
| Single-room vacuum via `start-vacuum-room-sweep` | **Confirmed** on hardware |
| `clean_mode` is `sweep_type`, not `sweep_mop_type` | **Confirmed** |
| Paused job causes whole-house fallback | **Confirmed** — reproduced from logs |
| Orphaned scripts survive `script.reload` | **Confirmed** — 19 orphans found |
| Multi-room (`"4,7"`) | **Unverified.** An earlier "confirmed" reading turned out to be a transient state caught before it flipped. |
| The 4 s reset guard actually prevents the fallback | **Unverified.** It targets the exact observed failure, but proving it requires deliberately reproducing a paused job. |

## License

MIT — see `LICENSE`.
