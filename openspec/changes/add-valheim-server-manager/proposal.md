## Why

Running a Valheim dedicated server today means hand-writing a `docker-compose.yml` against a container whose configuration surface is far larger than it first appears: roughly 60 environment variables, two cron schedules, 18 event hooks, seven log-filter prefixes, and a second, entirely separate gameplay surface expressed as Valheim CLI arguments rather than env vars. The sibling `minecraft-server` repo already proved the shape that makes this tractable — one richly-commented template plus a small dependency-free Python manager that scaffolds and runs named instances — and the same shape applies here.

The timing matters. Valheim 1.0 shipped 2026-09-09 and changed the on-disk world format from a single `.db`/`.fwl` pair to a directory of chunk files. The container image gained support for that the same day in v1.2.0. The older Docker Hub image (`lloesche/valheim-server`, last pushed 2026-03-18) predates the change and would take inconsistent backups of a 1.0 world, so getting the image reference right is now a correctness concern rather than a preference.

## What Changes

- Add `vh.py`, a dependency-free Python 3 manager (standard library only) with commands `ls`, `new`, `create`, `up`, `down`, `logs`, `backup`, `restart`, `status`, and `import`.
- Add a single richly-commented `templates/valheim.yml` documenting the container's full configuration surface, with everything optional commented out.
- Add a guided `create` wizard: a short essentials round, then an opt-in advanced round gated per topic (schedules, notifications, monitoring, log filters) so unwanted groups are skipped wholesale and never written to the generated file.
- Scaffold named instances into `instances/<name>/docker-compose.yml`, with per-instance config at `data/<name>/` and a **shared** SteamCMD server download at `server/`, so the ~1 GB payload is fetched once rather than per instance.
- Enforce one-running-server-at-a-time, mirroring `mc.py`'s port arbitration — `up` stops any other running instance first. This is what makes the shared server directory safe.
- Pin generated instances to `ghcr.io/community-valheim-tools/valheim-server` (tracking `latest`), with template comments explaining how to pin a version tag.
- Add `docs/` covering finding your server, world modifiers, and the Valheim 1.0 world-format migration.
- Add a `README.md` and `.gitignore` mirroring the sibling repo's conventions.
- Document modding (`BEPINEX`, `VALHEIM_PLUS`, the `VPCFG_*`/`BEPINEXCFG_*` env→cfg bridge) as commented-out template sections, but ship **no** mod tooling. Plugin management is deferred to a separate future change.

## Capabilities

### New Capabilities

- `server-templates`: The annotated `valheim.yml` blueprint and the `new` command that scaffolds an editable working copy from it.
- `instance-lifecycle`: Discovering, starting, stopping, and following logs for named instances, including single-server port arbitration and the shared/per-instance volume split.
- `guided-setup`: The `create` wizard — essentials round, per-topic advanced gates, confirmation summary, and generation of a clean minimal compose file.
- `server-operations`: On-demand `backup`, in-container `restart`, and `status` reporting against a running instance.
- `world-import`: Installing an existing Valheim world into an instance, detecting 1.0 directory saves versus pre-1.0 file pairs and warning about one-way conversion.

### Modified Capabilities

None — this is a greenfield repository with no existing specs.

## Impact

- **New files**: `vh.py`, `templates/valheim.yml`, `README.md`, `.gitignore`, `docs/*.md`, `instances/.gitkeep`, `data/.gitkeep`.
- **Gitignored runtime state**: `instances/*`, `data/*`, `server/*` — world saves, backups, and the ~1 GB Steam download are large and machine-specific.
- **External dependencies**: Docker with Compose v2, and Python 3 (standard library only — no pip installs, matching `mc.py`).
- **Container image**: `ghcr.io/community-valheim-tools/valheim-server`. Explicitly *not* `docker.io/lloesche/valheim-server`, which is stale and predates the Valheim 1.0 save format.
- **Host requirements**: UDP 2456–2457 (2458 additionally when crossplay is on); roughly 4 GB RAM minimum with a strong preference for few high-clocked cores.
- **Out of scope**: All mod tooling (BepInEx/ValheimPlus plugin installation, Thunderstore integration) — deferred to a follow-up change.
