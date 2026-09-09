# Valheim 1.0 worlds

Valheim 1.0 (9 September 2026) changed how a world is stored on disk. If you are
starting fresh you can ignore all of this. If you are bringing an existing world
with you, read the first two sections.

## The save format changed

**Before 1.0**, each world was two files in `worlds_local/`:

```
worlds_local/
├── Midgard.db      the world itself
├── Midgard.db.old  the previous save, always in a consistent state
└── Midgard.fwl     metadata (seed, name)
```

**On 1.0**, each world is a *directory* of many files:

```
worlds_local/
└── Midgard/
    ├── Midgard.fwl
    ├── ... chunk files ...
    └── _main.7.ok      marks the most recent committed save
```

This is why `WORLD_NAME` is described two ways: on 1.0 it is the **directory**
name inside `worlds_local/`, and on a pre-1.0 save it was the **filename without
the extension**. In both cases it is just `Midgard`.

## Upgrading an old world is one-way

The first time a 1.0 server opens a pre-1.0 world it rewrites it into the new
format. **An older server can never read it again.** As with every Valheim world
version upgrade, there is no downgrade path.

`vh.py import` handles this for you:

```bash
python vh.py import my-server ~/Downloads/Midgard.db
```

It detects which format you handed it, and for a pre-1.0 world it warns you and
offers to keep an untouched copy of the originals at
`data/<name>/pre-1.0-originals/<world>/` before installing anything. Say yes. It
costs a few megabytes and it is the only way back.

The conversion itself happens on the **first start after importing**, not during
the import — so the safety copy is taken before anything can touch the files.

Your source files are never modified: `import` copies, it does not move.

## Backups and the new format

A backup of a directory-shaped world is a harder problem than a backup of a single
file. Backups run while the server is live, so a backup started mid-save could
capture a chunk index that points at chunk files the server has already replaced.

The container handles this from image `1.2.0` onward: the server marks each
committed save with a `_main.<n>.ok` file, the backup job checks that marker, and
**retries up to three times** if the world was saved while it was being read. If
none of the attempts land between saves the backup is kept anyway, with a warning
in the log.

Two practical consequences:

- **Use an image that knows about this.** Instances generated here track
  `ghcr.io/community-valheim-tools/valheim-server:latest`, which does. The stale
  Docker Hub mirror (`lloesche/valheim-server`, last pushed March 2026) predates
  the format entirely.
- **`BACKUPS_IF_IDLE=false` makes it less likely.** Backups then only run around
  actual play, so there are simply fewer of them racing the save loop. The
  wizard's backups topic offers this.

With `BACKUPS_ZIP=false`, a backup of a 1.0 world is a **directory**, not a file.
Anything you point at `@BACKUP_FILE@` in a `POST_BACKUP_HOOK` — an offsite copy,
for instance — has to copy recursively (`scp -r`, `cp -r`, `rsync -a`).

## The `PUID` / `PGID` trap

The container runs as root by default, and that is the right setting here.

If you set a non-root `PUID`/`PGID` on **any image older than `1.2.0`**, the
permission logic applies the *file* mode to the new per-world *directories*,
stripping their execute bit. A directory without the execute bit cannot be
entered, so the server cannot open its own save. What you see is:

- `UnauthorizedAccessException` in the log, once, at startup;
- the server **keeps running**;
- the container reports healthy;
- no world is loaded and nobody can join.

Nothing else says anything is wrong. This is why `vh.py create` never offers
`PUID`/`PGID`, and why the template documents them with the warning attached. If
you genuinely need to run non-root, be on `1.2.0` or later first.

## Where worlds live on the machines you play on

`vh.py import` takes a path to any of these:

| Platform | Path |
| --- | --- |
| Windows | `%USERPROFILE%\AppData\LocalLow\IronGate\Valheim\worlds_local` |
| Linux | `~/.config/unity3d/IronGate/Valheim/worlds_local` |

(Those are the Steam client's paths. Non-Steam clients store worlds inside their
own platform's app data, and on console you cannot get at them at all.)

Copy the world out of there (the directory, or the `.db` **and** `.fwl` pair) and
point `import` at it. Inside this repo, each server's worlds live in
`data/<name>/worlds_local/`.
