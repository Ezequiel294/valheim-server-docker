# Valheim server manager

A small setup for running a Valheim dedicated server on any machine with Python
and Docker, built on
[`ghcr.io/community-valheim-tools/valheim-server`](https://github.com/community-valheim-tools/valheim-server-docker).

There are two ways to make a server. `vh.py create` runs a **guided wizard** that
asks plain-language questions and writes a clean, ready-to-run instance. Or, for
full control, `templates/valheim.yml` is a **richly-commented blueprint** you can
copy and hand-edit. Either way your real config lives under `instances/`
(gitignored); the template stays pristine.

## Layout

```
.
├── templates/
│   └── valheim.yml           the annotated blueprint — read this to learn the options
├── instances/                your servers (gitignored) — created by `vh.py create` / `new`
├── data/                     per-server state (gitignored) — data/<name>/
│                               worlds_local/  your worlds
│                               backups/       automatic + on-demand backups
│                               adminlist.txt  admins, bans, whitelist
├── server/                   the shared Valheim download, ~1 GB (gitignored)
├── docs/
│   ├── finding-your-server.md   how you and your friends actually connect
│   ├── valheim-on-arm.md        Raspberry Pi / ARM hosts, and what works there
│   ├── world-modifiers.md       difficulty, resources, raids, portals
│   └── valheim-1.0-worlds.md    the new save format, and upgrading an old world
└── vh.py                     the manager
```

## Workflow

```bash
# 1. see what's there
python vh.py ls

# 2a. guided: answer questions, get a clean instance file
python vh.py create              # -> instances/<name>/docker-compose.yml

# 2b. or copy the template and hand-edit it (keeps all the explanatory comments)
python vh.py new my-server       # -> instances/my-server/docker-compose.yml

# 3. run it (stops any other running server first — see below)
python vh.py up my-server
python vh.py logs my-server      # follow the log; Ctrl-C stops following, not the server

# day to day
python vh.py status my-server    # running? who's on? which version?
python vh.py backup my-server    # force a backup right now
python vh.py restart my-server   # restart the game process, keep the container
python vh.py down my-server      # stop and remove the container (the world is kept)
python vh.py                     # interactive menu (same commands)

# bringing an existing world with you
python vh.py import my-server ~/path/to/MyWorld
```

`vh.py` needs only Python 3 and Docker — no pip installs.

**The first start downloads about 1 GB** of Valheim dedicated server from Steam
into `server/`, so it takes several minutes and the server is not joinable until
it finishes. `vh.py logs` is how you watch it. That download is reused forever
after, including by every other instance you create.

## Two things worth knowing before you start

### One server at a time

Every instance binds the same host UDP ports (2456–2457) and mounts the same
`server/` download, so `vh.py up` **stops whatever else is running first** and
says so. This is deliberate, not a limitation waiting to be fixed: two servers
sharing one `server/` directory would race each other during a SteamCMD update.

Because `server/` sits next to `data/`, **`server` is a reserved instance name.**

Multiple instances are still useful — a hardcore world and a relaxed one, say —
you just play one at a time. Each keeps its own world, backups and admin lists
under `data/<name>/`, and switching between them costs one `up` command.

### There is no console command

Valheim has no RCON. Admin commands (`ban`, `kick`, `save`, `help`) are typed
**in-game** by an admin pressing **F5**, and recent Valheim versions need the
client launched with `-console` for F5 to open at all. Put your SteamID64 in
`ADMINLIST_IDS` (the wizard's access-control topic does this) and you are an
admin.

What the container offers instead is a process supervisor, and `vh.py` wraps the
two operations worth wrapping: `backup` and `restart`. Anything else is reachable
with `docker exec vh-<name> supervisorctl ...` if you ever need it.

## The container image

Generated instances use `ghcr.io/community-valheim-tools/valheim-server`, **not**
`docker.io/lloesche/valheim-server`. The project was transferred to the community
organisation and the GHCR image is the one still receiving builds; the Docker Hub
mirror stopped in March 2026 — months before Valheim 1.0 changed the on-disk world
format — and takes inconsistent backups of a 1.0 world. This is a correctness
difference, not a preference.

Instances track `latest`, so the container picks up save-format and SteamCMD fixes
as they land. To pin instead, add a tag in your instance file:

```yaml
image: ghcr.io/community-valheim-tools/valheim-server:1.2.0
```

Tags published so far: `latest`, `1.2.0`, `1.1.0`, `1.0.0`. `1.2.0` is the first
release that understands Valheim 1.0 world directories.

Note that the **game** updates on its own schedule regardless: the container
re-runs SteamCMD on `UPDATE_CRON` (every 15 minutes by default, only when nobody
is connected), so a new Valheim release arrives without a new image.

## Backups

Backups run on startup and hourly, into `data/<name>/backups/`, and are kept for
three days. They survive `vh.py down` — nothing under `data/` is removed by
stopping a server.

`vh.py backup <name>` forces one immediately. It **restarts** the container's
backup service rather than signalling it, because with `BACKUPS_IF_IDLE=false` a
signal only produces a backup if there has been recent player activity — which
would make "force a backup" quietly do nothing on the idle server where you most
want one.

## Stopping safely

Valheim writes the world to disk every 20 minutes and at shutdown. Every generated
instance sets `stop_grace_period: 2m` so the server gets time to finish that final
save, and `vh.py down` respects it. Killing the container faster loses the session.

## Modding

The template documents the container's BepInEx and ValheimPlus support — where
plugins go, and the `VPCFG_*` / `BEPINEXCFG_*` bridge that writes mod config from
environment variables. **`vh.py` does not manage plugins**: it never downloads,
installs, moves or deletes a mod file. Enabling a loader and putting `.dll` files
in `data/<name>/bepinex/plugins/` is yours to do.

## Architecture: this needs an x86_64 binary somewhere

Valheim's dedicated server is an **x86_64 Linux binary** and Iron Gate ships no
ARM build, so the image is published for `linux/amd64` only. What that costs you
depends entirely on what kind of ARM host you have — the two cases are not alike.

### Docker Desktop on an ARM Mac — does not work

Verified here on Apple Silicon. `platform: linux/amd64` gets the container to
start, but SteamCMD's core is a *32-bit* x86 binary and it segfaults loading the
Steam API under both of Docker Desktop's emulation backends, Rosetta and QEMU:

```
steamcmd.sh: line 86: Segmentation fault  $DEBUGGER "$STEAMEXE" "$@"
ERROR - Failed to download Valheim server from Steam - retrying later
```

The container comes up, reports healthy, and retries a download that cannot
succeed. Don't host from an ARM Mac.

### ARM Linux (Raspberry Pi 5, ARM SBCs) — viable, with setup

This is a different mechanism and a much better one.
[box64](https://github.com/ptitSeb/box64) translates x86_64 binaries to ARM64 in
userspace, running natively on Linux rather than emulating a whole machine. It is
actively maintained, and running Valheim on a Pi is a well-trodden use case —
people report a Pi 5 sitting at 30–40% CPU with two players.

Three things a Pi 5 needs:

1. **A 4K-page kernel.** The Pi 5 defaults to a 16K page size; box64 and box86
   need 4K. Add `kernel=kernel8.img` to `/boot/firmware/config.txt` and reboot.
   Costs roughly 5% general performance and is not optional.
2. **8 GB RAM or more.** Valheim idles around 2.8 GB before anyone connects.
3. **A USB SSD**, not a microSD card. Startup and world saves are the hitchy part.

Whether the *container* runs under box64 is a separate question from whether the
server does. Registering box64 with `binfmt_misc` (using the `F` flag, so the
interpreter survives the container's mount namespace) is reported to work but is
not a well-supported path yet — box64's static build is marked experimental. Try
it before assuming you need a custom image; see `docs/valheim-on-arm.md`.

### The path of least resistance

An x86_64 machine — an old PC, a NAS, a small VPS — runs everything here as
built, today, with no emulation and no caveats.

## Requirements

- Docker with Compose v2, and Python 3.
- **x86_64 for the simple path.** ARM Linux works via box64 with setup; an
  ARM Mac does not work at all (see above).
- ~4 GB RAM minimum, 8 GB recommended. Valheim leans on **a few fast cores** far
  more than on many slow ones — two 5 GHz cores beat six 2 GHz ones.
- UDP 2456–2457 reachable from the internet if you want people outside your
  network to join without crossplay (2458 as well when crossplay is on).
  See [docs/finding-your-server.md](docs/finding-your-server.md).
