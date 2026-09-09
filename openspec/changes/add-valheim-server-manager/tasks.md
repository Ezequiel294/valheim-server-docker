## 1. Repository scaffolding

- [ ] 1.1 Create the directory layout (`templates/`, `instances/.gitkeep`, `data/.gitkeep`, `docs/`) and verify `find . -not -path './.git/*' -not -path './openspec/*'` shows the expected tree
- [ ] 1.2 Write `.gitignore` ignoring `instances/*`, `data/*`, and `server/*` while keeping the `.gitkeep` files, and verify `git status --porcelain` stays clean after creating a dummy instance and data directory
- [ ] 1.3 Reserve `server` as an instance name in a shared constant and verify it is referenced by the name validator added in 5.2

## 2. Annotated template

- [ ] 2.1 Write `templates/valheim.yml` service skeleton — image `ghcr.io/community-valheim-tools/valheim-server`, `cap_add: sys_nice`, `restart: unless-stopped`, `stop_grace_period: 2m`, UDP `2456-2457` ports, and both volume mounts — and verify `docker compose -f <scaffolded copy> config` parses without error
- [ ] 2.2 Document the essentials group (`SERVER_NAME`, `WORLD_NAME`, `SERVER_PASS`, `SERVER_PORT`, `SERVER_PUBLIC`, `CROSSPLAY`) as live settings, noting the 5-character password minimum and that the query port is `SERVER_PORT + 1`; verify a copy edited only for identity starts a server
- [ ] 2.3 Document access control (`ADMINLIST_IDS`, `BANNEDLIST_IDS`, `PERMITTEDLIST_IDS`) as commented options, noting SteamID64 format and that they overwrite the on-disk lists; verify by inspection against the upstream variable table
- [ ] 2.4 Document backups (`BACKUPS*`), scheduling (`UPDATE_CRON`, `RESTART_CRON`, `*_IF_IDLE`), and the legacy `UPDATE_INTERVAL`/`BACKUPS_INTERVAL` deprecation warning as commented options; verify every variable in the upstream table appears exactly once
- [ ] 2.5 Document observability (`STATUS_HTTP*`, `SUPERVISOR_HTTP*`, `SYSLOG_REMOTE_*`), event hooks, and `VALHEIM_LOG_FILTER_*` as commented options, including the rule that log-filter variables are prefixes; verify by inspection against the upstream tables
- [ ] 2.6 Document the gameplay `SERVER_ARGS` section listing every preset, modifier category with its values, and setkey, plus the preset-before-modifier ordering rule; verify a hand-built example applies its modifier rather than discarding it
- [ ] 2.7 Document the modding section (`BEPINEX`, `VALHEIM_PLUS`, mutual exclusion, plugin directory, `VPCFG_*`/`BEPINEXCFG_*` bridge and its escape table) fully commented out, and verify no manager command references it
- [ ] 2.8 Document `PUID`/`PGID` with the non-root world-directory permission warning, `PERMISSIONS_UMASK`, `TZ`, and `SERVER_PASS_FILE`; verify by inspection that the warning names the silent-failure symptom
- [ ] 2.9 Add the image-pinning comment naming available tags, plus `template-only` scaffolding markers, and verify a scaffolded copy contains no marker text and no self-reference as a template

## 3. Manager foundation

- [ ] 3.1 Create `vh.py` with its module docstring, path constants, and command dispatch table; verify `python vh.py --help` prints usage and `python vh.py bogus` exits non-zero with a clear error
- [ ] 3.2 Implement template/instance discovery, `compose_file()`, `container()`, and `running_instances()`; verify `running_instances()` returns an empty set rather than raising when Docker is unavailable
- [ ] 3.3 Implement `run()`, `compose_cmd()`, `die()`, and `require_instance()`; verify `require_instance()` on an unknown name reports how to create one and exits non-zero

## 4. Lifecycle commands

- [ ] 4.1 Implement `ls` showing the template and each instance with running/stopped state; verify output against a checkout with two instances, one running
- [ ] 4.2 Implement `new <name>` — scaffold from the template, strip `template-only` blocks, substitute the instance name, refuse to overwrite; verify a scaffolded file differs from the template only in those two respects
- [ ] 4.3 Implement `up <name>` stopping any other running instance first; verify starting a second instance while a first runs prints the stop notice and leaves only one container running
- [ ] 4.4 Implement `down <name>` respecting the shutdown grace period; verify the server logs a world save before the container is removed
- [ ] 4.5 Implement `logs <name>` with clean exit on interrupt; verify Ctrl-C returns exit status 0 with no traceback and leaves the container running

## 5. Wizard — prompts and generation

- [ ] 5.1 Port the prompt helpers (`ask`, `ask_int`, `ask_yes_no`, `ask_choice`, `section`, `Abort`) with `?`-for-help; verify `?` at each prompt type prints help and re-asks without advancing
- [ ] 5.2 Implement instance-name validation — allowed characters, collision with an existing instance, and the reserved `server` name; verify each rejection re-prompts with an explanation
- [ ] 5.3 Implement the directive-list compose generator emitting scalars, literal blocks, and comment lines outside blocks; verify generated output parses under `docker compose config`
- [ ] 5.4 Implement the essentials round including the 5-character password check; verify declining all further configuration yields a runnable file containing only essentials

## 6. Wizard — advanced topic gates

- [ ] 6.1 Implement the advanced gate and the gameplay topic, serialising preset, then modifiers, then setkeys into `SERVER_ARGS`; verify a preset plus an overridden modifier emits them in an order that preserves the override
- [ ] 6.2 Implement the access-control topic collecting SteamID64 lists; verify declining it emits no list variables
- [ ] 6.3 Implement the backups topic including the `BACKUPS_IF_IDLE` consistency guidance in its help; verify declining it emits no backup variables
- [ ] 6.4 Implement the schedules topic for the three cron variables; verify an accepted-then-defaulted answer omits the variable rather than writing the default
- [ ] 6.5 Implement the notifications topic wiring a Discord webhook into selected hooks, warning about recursive copying when zipping is disabled; verify generated hook strings survive compose variable interpolation
- [ ] 6.6 Implement the monitoring topic (`STATUS_HTTP`, `SUPERVISOR_HTTP`, syslog), whose help explains the public-server dependency for live status; verify enabling status HTTP also exposes its port
- [ ] 6.7 Implement the log-filter topic; verify multiple filters of the same kind emit distinct suffixed variable names
- [ ] 6.8 Implement the summary, confirmation, and write step; verify declining writes nothing and interrupting mid-wizard leaves no partial instance directory

## 7. Operations commands

- [ ] 7.1 Implement `backup <name>` by restarting the backup service rather than signalling it, reporting the backup directory; verify a backup appears on an idle server configured with `BACKUPS_IF_IDLE=false`
- [ ] 7.2 Implement `restart <name>` restarting only the server process; verify the container ID is unchanged afterwards while the server has restarted
- [ ] 7.3 Implement `status <name>` reporting process state always and live details when available; verify a private server reports process state plus the settings needed for more, and a stopped instance reports not running
- [ ] 7.4 Verify every operations command on a stopped instance reports that it is not running instead of failing obscurely

## 8. World import

- [ ] 8.1 Implement world-format detection distinguishing a 1.0 directory, a pre-1.0 `.db`/`.fwl` pair, and neither; verify each of the three inputs is classified correctly
- [ ] 8.2 Implement the pre-1.0 conversion warning and optional retained safety copy; verify accepting it leaves an untouched copy whose location is reported
- [ ] 8.3 Implement installation into the instance's world directory, refusing to overwrite without explicit confirmation and leaving the source unmodified; verify both by checksum of the source and by the refusal path
- [ ] 8.4 Set and report the instance's `WORLD_NAME` for the detected format; verify the instance loads the imported world on next start rather than generating a new one
- [ ] 8.5 Verify importing into a nonexistent instance installs nothing and names the command that creates one

## 9. Entry points and documentation

- [ ] 9.1 Implement the interactive menu covering every command, surviving `die()` without exiting; verify an invalid command inside the menu prints an error and returns to the prompt
- [ ] 9.2 Write `README.md` — layout, workflow, the one-server-at-a-time rule, the shared `server/` directory, and the image choice with its rationale; verify a reader can go from clone to running server using only the README
- [ ] 9.3 Write `docs/world-modifiers.md` covering presets, modifier categories and values, setkeys, and the ordering rule; verify every value listed matches the upstream server manual
- [ ] 9.4 Write `docs/valheim-1.0-worlds.md` covering the directory save format, one-way conversion, backup consistency, and the non-root permissions warning; verify it matches the `1.2.0` release notes
- [ ] 9.5 Write `docs/finding-your-server.md` covering direct IP join, the community browser, Steam favourites on `port + 1`, and crossplay's effect on LAN discovery; verify each method against upstream documentation

## 10. End-to-end verification

- [ ] 10.1 Run the full wizard accepting only essentials, start the instance, and verify players can connect and the world persists across `down` then `up`
- [ ] 10.2 Run the full wizard accepting every topic gate, and verify the generated file parses, starts, and contains no setting the user did not choose
- [ ] 10.3 Create a second instance, verify it reuses the existing `server/` download without re-fetching, and verify `up` stops the first instance
- [ ] 10.4 Import a pre-1.0 world into a fresh instance, confirm the warning and safety copy, start the server, and verify the world converts and loads
- [ ] 10.5 Exercise `backup`, `restart`, and `status` against a running instance and verify each reports the documented outcome

