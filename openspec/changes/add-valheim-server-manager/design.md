## Context

See `proposal.md` — Why. Design-relevant constraints only:

The sibling `minecraft-server` repo establishes the conventions this one should follow: pristine blueprints in `templates/`, working copies in gitignored `instances/<name>/`, world state in gitignored `data/`, and a single dependency-free `mc.py` that scaffolds and drives them. Users moving between the two repos should not have to learn a second set of habits.

Three properties of the Valheim container break the direct analogy and shape everything below:

1. **Configuration lives in two surfaces.** Container behaviour (lifecycle, backups, hooks, observability) is environment variables. Gameplay (difficulty, combat, resources, raids, portals) is Valheim CLI arguments passed through a single `SERVER_ARGS` string. `itzg/minecraft-server` exposes both as env vars; this image does not.
2. **There is no RCON.** Valheim admin commands run in-game by an admin pressing F5. The container instead exposes a process supervisor reachable via `docker exec`. `mc.py console` has no counterpart.
3. **The server binary is a ~1 GB runtime download**, not part of the image, mounted separately from config.

Valheim 1.0 (2026-09-09) changed the on-disk world format from a `.db`/`.fwl` pair to a directory of chunk files. Image `v1.2.0`, released the same day, adapted the backup and permissions logic to it. This is recent enough that the format split must be handled explicitly rather than assumed away.

## Goals / Non-Goals

**Goals:**

- A user who knows `mc.py` can drive `vh.py` without reading anything.
- The template alone answers "what can I configure?" without a trip to upstream docs.
- The wizard's default path is short; its full path reaches every option group.
- Nothing the user did not choose appears in a generated file.
- Failure modes that are silent in the underlying container are made loud here.

**Non-Goals:**

- Multi-server-at-once operation. One host, one running server, as in the sibling repo.
- Any mod plugin management. Documented in the template, deferred as tooling.
- Wrapping the container's process supervisor as a general-purpose escape hatch.
- Managing host firewall or port forwarding.

## Decisions

### Image reference: `ghcr.io/community-valheim-tools/valheim-server`, tracking `latest`

The project was transferred from `lloesche/valheim-server-docker` to `community-valheim-tools/valheim-server-docker`; the GitHub API returns identical metadata for both names. The Docker Hub image did not follow — `docker.io/lloesche/valheim-server:latest` was last pushed 2026-03-18, six months before the world format changed, and would take inconsistent backups of a 1.0 world with no retry logic and no `.ok` marker awareness.

Tracking `latest` over pinning `1.2.0`: auto-updating is this image's core value, and today demonstrated that fixes land when the game moves. The cost — a pull can change behaviour under a running server — is mitigated by documenting the pin syntax and available tags in the template, and by `backup` existing as a one-command precaution.

**Alternatives considered:** pinning `1.2.0` in generated instances (reproducible, but silently freezes out the next save-format fix); using the Docker Hub mirror for familiarity (rejected — correctness).

### One template, not three

Splitting by mod framework would produce three files differing by one boolean, since Valheim has a single server binary. Splitting by "simple vs full" would force a guess about which options a given user considers advanced, and the wizard already answers that question dynamically. A single annotated `valheim.yml` therefore serves as both the hand-edit starting point and the reference document.

The wizard does **not** generate by filling in this template. It assembles a minimal file from an ordered list of directives, as `mc.py` does — so the wizard's output is clean and comment-free while the template stays exhaustively commented. Two outputs, two purposes.

### Shared server download, guarded by single-server arbitration

Layout:

```
templates/valheim.yml          blueprint
instances/<name>/              working copy      (gitignored)
data/<name>/                   per-instance /config: worlds, backups, lists  (gitignored)
server/                        shared /opt/valheim, ~1 GB, downloaded once   (gitignored)
```

Compose mounts, relative to `instances/<name>/`, mirroring `mc.py`'s `../../data/__INSTANCE__` idiom:

```
../../data/<name>:/config
../../server:/opt/valheim
```

Sharing `server/` is only safe because `up` stops any other running instance first — the same arbitration `mc.py` applies to port 25565, needed here anyway because all instances bind the same host UDP ports. Two servers sharing the directory could otherwise race on a steamcmd update. Because `server/` sits alongside `data/`, `server` is a reserved instance name.

**Alternatives considered:** per-instance `data/<name>/server/` (safe unconditionally, but ~1 GB per instance and a slow first boot each time, for isolation that the one-at-a-time rule already provides).

### Wizard: essentials, then per-topic gates

```
── Essentials ────────────────────────────
   name · SERVER_NAME · WORLD_NAME · SERVER_PASS
   SERVER_PUBLIC · CROSSPLAY
                    │
   Configure advanced settings? ──── no ──▶ summary
                    │ yes
   ┌────────────────┴─────────────────────┐
   │ Gameplay?      preset/modifiers/setkeys
   │ Access?        ADMINLIST/BANNEDLIST/PERMITTEDLIST
   │ Backups?       retention, if-idle, zip
   │ Schedules?     BACKUPS/RESTART/UPDATE_CRON
   │ Notifications? DISCORD_WEBHOOK + hook selection
   │ Monitoring?    STATUS_HTTP, SUPERVISOR_HTTP, SYSLOG
   │ Logs?          VALHEIM_LOG_FILTER_*
   └──────────────────────────────────────┘
                    │
              summary → confirm → write
```

Each group is a yes/no gate, so declining skips the whole block. A flat advanced round covering this surface would be punishingly long. The `?`-for-help convention, the summary-before-write, and the directive-list generator are carried over from `mc.py` unchanged.

### Gameplay settings assembled as an ordered `SERVER_ARGS` string

`-preset` appearing after `-modifier` silently discards the modifier. The wizard therefore collects gameplay answers into a structure and serialises them in fixed order — preset, then modifiers, then setkeys — rather than appending as it asks. The template documents the same ordering rule for hand-editors.

### Force-backup restarts the backup service rather than signalling it

Both `supervisorctl signal HUP valheim-backup` and `supervisorctl restart valheim-backup` trigger a backup, but under `BACKUPS_IF_IDLE=false` the signal only produces one if there has been recent player activity — a "force a backup" command that silently does nothing on an idle server is a trap. Restarting the service always backs up, so `backup` uses restart.

### `status` reports what it can and says what it cannot

Process state comes from the container's supervisor and is always available. Player count and version come from `status.json`, which requires both `STATUS_HTTP=true` and `SERVER_PUBLIC=true` — private servers do not answer Steam queries. Rather than erroring or fabricating, `status` reports process state and names the settings that would enable the rest. The monitoring topic's help text explains the same dependency.

### No supervisor passthrough

A raw `supervisorctl` passthrough would be the only command whose surface is the container's internals rather than the server. Each wrapped operation (`backup`, `restart`) states an outcome instead. Anything unwrapped remains reachable by `docker exec` directly, which the docs note.

### `PUID`/`PGID` stay at their default

The image defaults to running as root. Setting a non-root UID on images older than `1.2.0` applies the *file* permission mode to the new per-world directories, stripping the execute bit; the server then logs `UnauthorizedAccessException`, keeps running, and serves no world while appearing healthy. The wizard does not offer these, and the template documents them with that warning attached.

### Python 3 standard library only

Matches `mc.py`. Everything needed — `subprocess`, `pathlib`, `shutil`, `json`, `urllib` — is stdlib. No pip install step in any documented workflow.

## Risks / Trade-offs

- **Two servers started outside `vh.py` corrupt the shared `server/` directory** → `up` arbitrates; `server` is a reserved instance name; the README states the one-at-a-time rule as a property of the design, not an incidental limitation.
- **`latest` can move under a running server** → pin syntax and tag list documented in the template; `backup` is one command; `restart` is faster than a full recreate if a pull misbehaves.
- **Pre-1.0 world conversion is irreversible** → `import` detects the format, warns, and offers a retained safety copy before installing; a docs page covers the migration.
- **Backups taken mid-save can capture an inconsistent chunk index** → the `1.2.0` image detects this via the `_main.<n>.ok` marker and retries up to three times, then keeps the backup with a warning. The backups topic's help explains that `BACKUPS_IF_IDLE=false` makes the situation far less likely, since backups then only run around player activity.
- **`BACKUPS_ZIP=false` produces a directory, not a file** → any templated `POST_BACKUP_HOOK` example copies recursively; the notifications topic warns when the user has disabled zipping.
- **The password sits in plaintext in the generated compose file** → `instances/` is gitignored; the template documents `SERVER_PASS_FILE` for users who want a secrets mount.
- **A long wizard is still a long wizard when every gate is accepted** → accepted. The gates make the common path short; the exhaustive path is opt-in by construction.
- **Setting the legacy `UPDATE_INTERVAL` or `BACKUPS_INTERVAL` silently disables the corresponding cron** → the wizard never emits them; the template documents them only as a deprecation warning.

## Migration Plan

Greenfield repository — nothing to migrate, and no rollback beyond deleting a generated instance directory.

The one migration-shaped path is a user adopting an existing world:

1. `vh.py create` or `vh.py new` to make the instance.
2. `vh.py import <name> <path>` — detects the format, warns on pre-1.0, offers the safety copy.
3. `vh.py up <name>`; a pre-1.0 world converts on first open and is thereafter unreadable by older servers.

Reverting to a pre-1.0 server after step 3 requires the safety copy, which is why `import` offers it rather than mentioning it.

## Open Questions

- Whether the docs should carry a Steam server-browser walkthrough or simply link upstream's, which is screenshot-heavy and kept current. Affects `docs/` breadth only.
- Whether `ls` should surface each instance's configured world name alongside its run state. Additive; no spec or task restructuring either way.
