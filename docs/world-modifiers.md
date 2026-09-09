# World modifiers

Valheim's difficulty and world rules are **command-line arguments**, not
environment variables. The container passes whatever you put in `SERVER_ARGS`
straight to `valheim_server.x86_64`, so this one string is the whole gameplay
surface:

```yaml
SERVER_ARGS: "-preset hard -modifier deathpenalty easy -setkey playerevents"
```

`vh.py create`'s gameplay topic builds this string for you. This page is for
hand-editing, and for understanding what you picked.

## The ordering rule

**The server reads arguments left to right, and `-preset` resets every modifier
before it.** So this:

```yaml
SERVER_ARGS: "-modifier combat veryhard -preset casual"   # ✗ combat setting lost
```

silently throws the combat setting away — no warning, no log line, the world just
runs at casual. Always write them in this order:

```
-preset  →  -modifier  →  -setkey
```

```yaml
SERVER_ARGS: "-preset casual -modifier combat veryhard"   # ✓ override survives
```

`vh.py` collects your answers first and serialises them in that order afterwards,
so the wizard cannot produce the broken form.

## `-preset` — the whole package

A preset sets every modifier at once. Pick one, or none for a standard world.

| Preset | What it is for |
| --- | --- |
| `normal` | Standard Valheim. The same as passing nothing. |
| `casual` | Gentler combat and death penalty, easier logistics. |
| `easy` | Softer than standard, still recognisably Valheim. |
| `hard` | Enemies hit harder and take more; harsher death penalty. |
| `hardcore` | The harshest package. |
| `immersive` | Removes convenience: no map, no portals. |
| `hammer` | Creative building — no build cost, creatures leave you alone. |

## `-modifier` — the individual dials

Each category has an unnamed *standard* setting. **To keep a category at
standard, don't pass it at all** — there is no `standard` value to type.

| Category | Values | What it changes |
| --- | --- | --- |
| `combat` | `veryeasy` `easy` `hard` `veryhard` | How hard enemies hit, and how much punishment they take. |
| `deathpenalty` | `casual` `veryeasy` `easy` `hard` `hardcore` | What you lose on death — skill loss, and whether your gear stays on your tombstone. |
| `resources` | `muchless` `less` `more` `muchmore` `most` | Drop rates from mining, foraging and creatures. |
| `raids` | `none` `muchless` `less` `more` `muchmore` | How often base attacks happen. `none` turns them off entirely. |
| `portals` | `casual` `hard` `veryhard` | What may travel through a portal. `casual` lets ore and metals through; `veryhard` disables portals altogether. |

Syntax is `-modifier <category> <value>`, one flag per category:

```yaml
SERVER_ARGS: "-modifier resources muchmore -modifier raids less"
```

## `-setkey` — the on/off switches

Applied on top of the preset and modifiers. Each is a bare flag.

| Key | Effect |
| --- | --- |
| `nobuildcost` | Building consumes no materials. |
| `playerevents` | Raids and events trigger per player rather than per world. |
| `passivemobs` | Creatures never attack first. |
| `nomap` | No map at all — no map sharing, no death markers. |

```yaml
SERVER_ARGS: "-setkey nobuildcost -setkey passivemobs"
```

Valheim recognises further global keys in the in-game console (F5), but the four
above are the ones the dedicated server documents as startup flags. The
authoritative list ships with the download itself, as
`server/Valheim Dedicated Server Manual.pdf`, once the container has fetched it.

## Changing modifiers on a running world

Modifiers are applied at startup, so:

1. Edit `SERVER_ARGS` in `instances/<name>/docker-compose.yml`.
2. `python vh.py down <name>` then `python vh.py up <name>`.

`vh.py restart` is **not** enough — it restarts the game process inside the
existing container, which was started with the old arguments. Changing arguments
needs the container recreated, which is what `down` + `up` does.

Take a backup first if you are making a big change:

```bash
python vh.py backup <name>
```

## A note on achievements

Valheim 1.0 added achievements, and cheats disable them. Iron Gate has not stated
whether presets or individual modifiers do the same. If achievements matter to
your group, assume a modified world may not award them.
