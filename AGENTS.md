# Agent install guide

Instructions for an AI coding agent installing and configuring this package on a
live Home Assistant instance. A human following this by hand is fine too, but
the procedure is written to be executed by an agent with real access.

Read this file end to end before touching anything. The discovery steps are not
optional — this package **cannot** be installed correctly without substituting
values read from the target system.

## What you need access to

At least one of:

- **A shell inside the Home Assistant container/OS.** Config lives at `/config`
  (`/homeassistant` on some installs). Gives you file writes and log access.
- **A long-lived access token** for the REST and WebSocket APIs. Create one
  under the user profile → Security → Long-lived access tokens.

Both is best: the shell to write `scripts.yaml`, the API to read live state and
to reload without a restart.

Verify before proceeding:

```bash
curl -s -H "Authorization: Bearer $HA_TOKEN" http://<ha-host>:8123/api/ | jq .
# -> {"message": "API running."}
```

## Rules

1. **Never start the robot without asking.** Every script in this package moves
   a physical machine in someone's home. Dispatch a real clean only with
   explicit consent, and say which room you are about to send it to.
2. **Back up before writing.** `cp /config/scripts.yaml /config/scripts.yaml.bak-$(date +%Y%m%d)`.
3. **Do not invent entity IDs.** Read them. They encode account region and
   device id, and a plausible-looking guess will silently do nothing.
4. **Do not report a step as verified from a state read alone.** See
   [Verification](#verification) — this system has a specific trap here.
5. Leave `secrets.yaml`, `.storage/` and tokens out of anything you commit.

## Step 1 — Confirm the integration and find the vacuum

The vacuum must already be connected through the `xiaomi_home` HACS
integration. Confirm the entity exists:

```bash
curl -s -H "Authorization: Bearer $HA_TOKEN" \
  http://<ha-host>:8123/api/states \
  | jq -r '.[].entity_id | select(startswith("vacuum."))'
```

Expect something like `vacuum.xiaomi_cn_123456789_ov42gl`. Everything after
`vacuum.` is **the prefix** you will substitute throughout. Record it.

If nothing matches, stop: the integration is not set up, and that is a
prerequisite this package does not cover.

## Step 2 — Confirm the MIoT action entities exist

```bash
curl -s -H "Authorization: Bearer $HA_TOKEN" \
  http://<ha-host>:8123/api/states \
  | jq -r '.[].entity_id | select(contains("<prefix>"))' | sort
```

You need all of these to be present:

| Purpose | Entity |
|---|---|
| Room sweep action | `notify.<prefix>_start_vacuum_room_sweep_a_2_16` |
| Stop / end job | `button.<prefix>_stop_working_a_2_51` |
| Vacuum vs mop | `select.<prefix>_sweep_mop_type_p_2_4` |
| Suction | `select.<prefix>_mode_p_2_9` |
| Water level | `select.<prefix>_mop_water_output_level_p_2_10` |
| Room list | `sensor.<prefix>_room_information_p_2_16` |
| Whole-house starts | `button.<prefix>_start_only_sweep_a_2_4`, `_start_mop_a_2_5`, `_start_sweep_mop_a_2_6` |

The numeric suffixes are MIoT `siid`/`piid`/`aiid` coordinates. **If any differ
on the target model, the model's spec differs** — resolve it against
`https://miot-spec.org/miot-spec-v2/instance?type=<urn>` and adjust
`scripts.yaml` accordingly rather than forcing the IDs above.

## Step 3 — Read the room IDs

```bash
curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "http://<ha-host>:8123/api/states/sensor.<prefix>_room_information_p_2_16" \
  | jq -r '.state'
```

```json
{"rooms": [{"id": 3, "name": "Living room"}, {"id": 4, "name": "Kitchen"}], "map_uid": 1}
```

If `rooms` is empty, there is no saved map — the human must create and name
rooms in the Xiaomi Home app first. This is not something you can fix from HA.

## Step 4 — Substitute and install

```bash
sed -i "s/xiaomi_xx_000000000_ov42gl/<prefix>/g" scripts.yaml
```

Then rewrite the per-room script bodies so each `rooms:` list matches the IDs
from Step 3, and translate every `alias:` into **the language the household
speaks to its voice assistant**. The alias is the spoken trigger; the entity ID
is not. Leave entity IDs, field names and comments in English.

Append the result to `/config/scripts.yaml` (backup first), or install it as a
package under a `script:` key.

## Step 5 — Reload, and deal with orphans

```bash
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
  http://<ha-host>:8123/api/services/script/reload
```

**`script.reload` does not delete scripts removed from YAML.** Entities from a
previous install survive in the entity registry, stay exposed to the voice
assistant, and keep firing their old definitions. After any rename, compare
what exists against what the YAML defines:

```bash
curl -s -H "Authorization: Bearer $HA_TOKEN" http://<ha-host>:8123/api/states \
  | jq -r '.[].entity_id | select(startswith("script."))' | sort
```

Anything present but no longer in the YAML is an orphan. Remove it via the
WebSocket API (`config/entity_registry/remove`) or Settings → Devices &
Services → Entities. Skipping this produces the confusing symptom of a voice
command running a definition that no longer exists in any file.

## Step 6 — Expose to the voice assistant

Expose the `vacuum_*`, `mop_*`, `clean_*` and `robot_go_home` scripts.
**Do not expose the two `vacuum_helper_*` scripts** — they take parameters and
are meaningless as scenes.

Via WebSocket, `homeassistant/expose_entity` with
`assistants: ["cloud.alexa"]` and `should_expose: true`. Confirm the new
entities are actually exposed rather than assuming the default carried them.

Home Assistant maps a script to Alexa's `SceneController`, so the phrasing is
*"turn on \<alias\>"*.

## Verification

This is where an agent is most likely to report a false success.

**The accepted cleaning config is transient.** Reading
`current_cleaning_config` a few seconds after dispatch can show a room
selection that is about to be discarded — this exact mistake was made during
development and reported as confirmed. Observed:

```
18:20:00  CFG {"rooms":[7],"clean_mode":3}   accepted
18:20:02  CFG {"clean_mode":1}                2s later: whole-house instead
```

The cause: **a previous job left paused makes the robot discard the room
selection and clean the whole house.** The scripts guard against this by
pressing `stop_working` and waiting 4 s when not docked.

So, to verify a room clean actually worked:

1. Confirm the robot is `docked` before dispatch.
2. Dispatch, then poll `current_cleaning_config` for **at least 15 seconds**,
   not once at +5 s.
3. Confirm `clean_mode` has not reverted to `1`.
4. Confirm against where the robot physically goes. State reads alone are not
   proof.

Also note `clean_mode` is `sweep_type` (job shape: whole-house / zone / area),
**not** `sweep_mop_type` (vacuum vs mop). Do not report "mode 3 = vacuum+mop".

`get-room-configs` returns HTTP 200 for any string, including garbage. It
cannot validate a room ID format. Only a real run can.

## Reporting back

State plainly which of these you verified on hardware and which you did not.
The two items most likely to remain unproven are **multi-room selection**
(`"4,7"`) and **the 4 s reset guard**, since proving the guard requires
deliberately reproducing a paused job. Say so rather than implying coverage.
