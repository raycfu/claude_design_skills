---
name: reel-builder
description: "Turns a set of effect clips into the viral 'I typed a command and Claude edited my video' reel: a chat screen types /effect-name, the edit builds out of glowing dots inside a card, zooms full screen, and the reel ends on a 'Comment WORD' grid of your edits. Adds keyboard typing sounds only, so you can lay your own music on top. Trigger with /reel-builder or phrases like 'make the chat reel', 'wrap my effects in the Claude chat format', 'build the comment-for-the-prompt reel'."
---

# /reel-builder

Wraps 4 to 8 edited clips in a chat-style reel. It is the format where a phone screen types `/glass-widgets`,
Claude says "Editing with glass-widgets...", the clip builds out of orange dots, zooms to full screen for 2 seconds,
and the reel ends on a "Comment EFFECT" grid. Everything is drawn in code, so it renders the same on any machine.

`SK` is this skill's folder. It reuses the Python environment of the effects skill
(`~/.claude/skills/effects/.venv`). If that does not exist, run `bash ~/.claude/skills/effects/scripts/setup.sh` first.
`PY` = `~/.claude/skills/effects/.venv/bin/python` (on Windows `.venv\Scripts\python.exe`).

## 1. Collect the clips

For each effect you need two files of the same moment:
- `raw`: the clip before the effect (shown as the attached thumbnail in the chat)
- `edited`: the clip with the effect, from the effects skill (`yourclip_effects.mp4`)

Make each edited clip at least 4 seconds long and render it a little longer than needed, so the effect never fades out
on screen. Vertical 1080x1920 is ideal; anything else is scaled to fit.

## 2. Pick the moment for each effect

Every effect shows its clip for `T_FULL + full_seconds` (2.2 s in the chat card, then `full_seconds` full screen, default 2).
`offset` is where in the edited clip that window starts. Choose it so the full-screen part lands on the payoff:
the last checklist tick, the graph hitting its number, the person pointing at the sign. Check with stills (step 4).

## 3. Write the config

Copy `SK/examples/config.json` next to the clips and edit it. Ask the user for:
- their first name for the greeting (`"greeting": "Evening, <name>"`)
- the comment keyword for the CTA (`cta_word`, e.g. `EFFECT`) and the pill line under it (`cta_pill`)
- which effect opens the reel (`cold_open.effect`, an index into `effects`) and its three words (`cold_open.lines`)
- up to 8 clips for the end grid (`grid`, each with a label, a clip and the time of a good frame)
- optional `more_label` like `+43 more effects`

Keys you can set: `output`, `full_seconds`, `end_seconds`, `cold_open` (`effect`, `from`, `seconds`, `lines`; leave it out
for no cold open), `effects[]` (`name`, `desc`, `raw`, `edited`, `offset`), `greeting`, `end_command`, `end_desc`,
`cta_word`, `cta_pill`, `more_label`, `reply_line1`, `reply_line2`, `grid_title`, `grid_subtitle`, `grid[]` (`label`, `clip`, `t`).
Paths are relative to the config file.

## 4. Check, then render

1. `"PY" "SK/scripts/reel.py" config.json --info` prints the length.
2. `"PY" "SK/scripts/reel.py" config.json --test 3.0 5.5 9.0 ...` saves `check_XX.XX.jpg` stills next to the config.
   Check the start and the end of every full-screen window (cycle k starts at `cold_open.seconds + k * 4.2`,
   full screen runs from +2.2 to +4.2). Look at them yourself. Adjust `offset` until every window ends on its payoff.
3. `"PY" "SK/scripts/reel.py" config.json` renders three files: the reel with typing sounds, a silent copy and
   the typing sounds as a WAV, so the user can mix their own music. Use `--crf 5` for the highest quality, `--jobs N`
   to use more CPU cores.

## Rules

- No brand logos. The working indicator is an original spinning ring, on purpose. Do not draw or paste another
  company's logo into the reel, even if the user supplies the file.
- No burned-in captions over the full-screen clips. Let the effect carry the moment.
- Keep the typing sounds as the only audio unless the user asks for music.
