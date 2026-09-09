#!/usr/bin/env python3
"""
vh.py — a tiny, dependency-free manager for the Valheim server template.

templates/valheim.yml is a pristine blueprint. This script scaffolds a named
*instance* from it (a working copy under instances/<name>/), then brings it
up/down with docker compose. No pip installs — Python 3 standard library only.

Usage:
    python vh.py                     # interactive menu
    python vh.py ls                  # list the template + instances (with status)

    python vh.py create              # guided wizard — asks questions, writes a
                                     #   clean instance (no explanatory comments)
    python vh.py new <name>          # or copy the annotated template to edit

    python vh.py up <name>           # start (stops any other running instance)
    python vh.py down <name>         # stop and remove the container
    python vh.py logs <name>         # follow the server log (Ctrl-C to stop)

    python vh.py backup <name>       # force a world backup right now
    python vh.py restart <name>      # restart the game process, keep the container
    python vh.py status <name>       # is it running, who's on, which version
    python vh.py import <name> <path>   # install an existing world into <name>

One host runs one Valheim server at a time: every instance binds the same UDP
ports and shares the same downloaded server, so `up` stops whatever else is
running first.

There is no console command — Valheim has no RCON. Admin commands (ban, kick,
save) are typed in-game by an admin pressing F5.
"""
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = ROOT / "templates"
INSTANCES_DIR = ROOT / "instances"
DATA_DIR = ROOT / "data"
SERVER_DIR = ROOT / "server"          # shared /opt/valheim — the ~1 GB download
ENV_FILE = ROOT / ".env"
PLACEHOLDER = "__INSTANCE__"
COMPOSE = ["docker", "compose"]
IMAGE = "ghcr.io/community-valheim-tools/valheim-server"

# server/ lives next to data/ and holds the shared Steam download, so an
# instance called "server" would be ambiguous at best. See _valid_name().
RESERVED_NAMES = {SERVER_DIR.name}

# Container-side defaults we need to know about to report useful paths.
DEFAULT_BACKUPS_DIRECTORY = "/config/backups"
DEFAULT_STATUS_HTDOCS = "/opt/valheim/htdocs"
SERVER_STATUS_FILE = "/var/run/valheim/valheim-server.status"

# --- Valheim gameplay surface (see docs/world-modifiers.md) ------------------
PRESETS = ["normal", "casual", "easy", "hard", "hardcore", "immersive", "hammer"]
MODIFIERS = {
    "combat": ["veryeasy", "easy", "hard", "veryhard"],
    "deathpenalty": ["casual", "veryeasy", "easy", "hard", "hardcore"],
    "resources": ["muchless", "less", "more", "muchmore", "most"],
    "raids": ["none", "muchless", "less", "more", "muchmore"],
    "portals": ["casual", "hard", "veryhard"],
}
SETKEYS = {
    "nobuildcost": "Building costs no materials",
    "playerevents": "Raids trigger per player rather than per world",
    "passivemobs": "Creatures never attack first",
    "nomap": "No map, no map sharing, no death markers",
}
LOG_FILTER_KINDS = ["MATCH", "STARTSWITH", "ENDSWITH", "CONTAINS", "REGEXP"]

# Container defaults for the scheduling questions. Answering with the default
# means "leave it alone", and the variable is not written at all.
CRON_DEFAULTS = {
    "BACKUPS_CRON": "5 * * * *",
    "UPDATE_CRON": "*/15 * * * *",
    "RESTART_CRON": "10 5 * * *",
}

# --- on-demand explanations printed when the user types "?" at a prompt ------
HELP_NAME = (
    "A short label for this server (folder + container name). Use letters,\n"
    "digits, '-' or '_'. Example: friends, hardcore, testing.\n"
    "'server' is reserved — that directory holds the shared game download."
)
HELP_SERVER_NAME = (
    "The name players see in the in-game Community browser and in Steam's server\n"
    "list. Spaces are fine. This is cosmetic and can differ from the instance name."
)
HELP_WORLD_NAME = (
    "Which world to load. On Valheim 1.0 this is the DIRECTORY name inside\n"
    "worlds_local/; on older saves it is the filename without .db/.fwl.\n"
    "If no world by that name exists, the server generates a fresh one.\n"
    "Importing an existing world later? Use 'vh.py import' — it sets this for you."
)
HELP_PASSWORD = (
    "Required to join. MINIMUM 5 CHARACTERS — with a shorter one the server\n"
    "process refuses to start and the container just sits there looking fine.\n"
    "It also may not appear inside the server name or the world name.\n"
    "It is stored in plain text in the generated file (instances/ is gitignored)."
)
HELP_PUBLIC = (
    "Yes — the server is listed in the in-game Community browser and answers\n"
    "  Steam queries (which is what makes the status page and Steam's server\n"
    "  browser work). Players still need the password.\n"
    "No  — the server is unlisted. People can still join with 'Join IP' in-game,\n"
    "  but Steam's browser, LAN favourites and the status page stop working."
)
HELP_CROSSPLAY = (
    "Yes — Xbox, Microsoft Store, Apple App Store and console players can\n"
    "  join.\n"
    "  Switches matchmaking from Steam to PlayFab and opens a third UDP port\n"
    "  (2458). Steam LAN discovery stops working, and some mods misbehave.\n"
    "No  — Steam clients only (Windows, Linux, macOS, Steam Deck)."
)
HELP_ADVANCED = (
    "The essentials above are enough for a working server. The advanced round\n"
    "walks seven optional topics — gameplay difficulty, access control, backups,\n"
    "schedules, notifications, monitoring, log filters — and each one asks first,\n"
    "so you can skip whole groups. Anything you skip stays at the container's\n"
    "default and is not written to the file at all."
)
HELP_PRESET = (
    "A preset sets every modifier at once:\n"
    "  normal     — standard Valheim\n"
    "  casual     — gentler combat and death penalty, easier logistics\n"
    "  easy       — softer than standard, still recognisably Valheim\n"
    "  hard       — tougher enemies, harsher death penalty\n"
    "  hardcore   — the harshest package\n"
    "  immersive  — removes convenience: no map, no portals\n"
    "  hammer     — creative building: no build cost, passive creatures\n"
    "You can pick a preset AND override individual dials afterwards — the wizard\n"
    "writes them in the right order so your overrides survive."
)
HELP_MODIFIERS = (
    "Individual dials. Each has an unnamed 'standard' setting — leave a category\n"
    "alone and it stays there.\n"
    "  combat        how hard enemies hit and how much they take\n"
    "  deathpenalty  what you lose on death (skill loss, tombstone rules)\n"
    "  resources     drop rates from mining, foraging and creatures\n"
    "  raids         how often base attacks happen ('none' turns them off)\n"
    "  portals       what may travel through portals; veryhard = no portals"
)
HELP_SETKEYS = (
    "On/off switches applied on top of the preset and modifiers:\n"
    "  nobuildcost   building consumes no materials\n"
    "  playerevents  raids trigger per player instead of per world\n"
    "  passivemobs   creatures never attack first\n"
    "  nomap         no map at all — no sharing, no death markers"
)
HELP_ADMINLIST = (
    "SteamID64s (17 digits, e.g. 76561198000000000), space separated. A player's\n"
    "ID shows in-game with F2 and in the server log when they connect.\n"
    "Admins get the F5 in-game console (ban, kick, save). Their client must be\n"
    "launched with -console for F5 to open.\n"
    "WARNING: this OVERWRITES /config/adminlist.txt on every start — manage the\n"
    "list here or in the file, never both."
)
HELP_BANNEDLIST = (
    "SteamID64s barred from joining, space separated. Overwrites\n"
    "/config/bannedlist.txt on every start."
)
HELP_PERMITTEDLIST = (
    "A whitelist. If this is non-empty, ONLY these SteamID64s may join — everyone\n"
    "else is refused even with the correct password. Leave empty for an open\n"
    "server. Overwrites /config/permittedlist.txt on every start."
)
HELP_BACKUPS = (
    "The container backs up worlds_local/ on startup and on a schedule, into this\n"
    "instance's own data directory, so backups survive 'vh.py down'.\n"
    "You can always force one with 'vh.py backup <name>'."
)
HELP_BACKUPS_IF_IDLE = (
    "Yes — back up on schedule even when nobody is online. Simple and safe.\n"
    "No  — only back up around actual play. Two reasons to prefer this: far less\n"
    "  disk churn, and fewer chances of catching the world mid-save. A Valheim\n"
    "  1.0 world is a directory of chunk files, so a backup taken while the\n"
    "  server is writing can capture an index pointing at replaced chunks. The\n"
    "  container detects that (the world carries a _main.<n>.ok marker) and\n"
    "  retries up to three times, but taking fewer needless backups helps."
)
HELP_BACKUPS_GRACE = (
    "Seconds after the last player disconnects during which backups still run.\n"
    "Keep it comfortably above 20 minutes: Valheim only saves the world every 20\n"
    "minutes, so a shorter grace period can miss the save containing the session\n"
    "you just played. It also has to outlast one tick of the backup schedule."
)
HELP_BACKUPS_ZIP = (
    "Yes — each backup is one .zip file. Smaller, and easy to copy around.\n"
    "No  — backups are stored uncompressed. On Valheim 1.0 that means each backup\n"
    "  is a DIRECTORY, so anything you point at it (an offsite copy hook, for\n"
    "  instance) has to copy recursively."
)
HELP_MAX_AGE = "Delete backups older than this many days. Always enforced."
HELP_MAX_COUNT = (
    "Keep at most this many backups, deleting the oldest first. 0 means no limit.\n"
    "The age limit still applies either way — old backups go regardless."
)
HELP_CRON = (
    "Standard five-field cron: minute hour day-of-month month day-of-week.\n"
    "  5 * * * *      hourly at :05        */15 * * * *   every 15 minutes\n"
    "  10 5 * * *     daily at 05:10       0 4 * * 0      Sundays at 04:00\n"
    "Times are in the container's time zone — set TZ if you care.\n"
    "Answer 'off' to disable the schedule entirely."
)
HELP_UPDATE_CRON = (
    "How often the container checks Steam for a new Valheim version. This is how\n"
    "the GAME stays current — a new game release is picked up here, without\n"
    "needing a new container image. Leave it alone unless you have a reason.\n"
    "Answer 'off' to disable update checks."
)
HELP_RESTART_CRON = (
    "A daily restart of the game process. Valheim's memory use creeps up over\n"
    "days; a nightly restart clears it. Answer 'off' to disable it."
)
HELP_IF_IDLE = (
    "Only act when nobody is connected, so players are never yanked out\n"
    "mid-session. The job waits for the next scheduled tick instead."
)
HELP_TZ = (
    "The container's time zone, which is what the cron schedules above are\n"
    "interpreted in. Examples: Etc/UTC, Europe/Berlin,\n"
    "America/Argentina/Buenos_Aires."
)
HELP_DISCORD = (
    "Paste a Discord webhook URL (channel settings -> Integrations -> Webhooks).\n"
    "The wizard wires it into the container's event hooks you choose below.\n"
    "The URL is a secret — anyone holding it can post to that channel. It is\n"
    "stored in plain text in the generated file (instances/ is gitignored)."
)
HELP_HOOK_PICK = (
    "Which moments should post a message:\n"
    "  server up       once the server is actually accepting players\n"
    "  restart warning just before a scheduled restart\n"
    "  backup done     after each backup completes\n"
    "  player spawned  whenever someone joins the world"
)
HELP_STATUS_HTTP = (
    "A tiny web server publishing /status.json (player count, version, server\n"
    "name) every 10 seconds — handy for a dashboard or an uptime monitor.\n"
    "IT ONLY WORKS ON A PUBLIC SERVER. The data comes from the Steam query port,\n"
    "and a server with SERVER_PUBLIC=false does not answer queries: you would get\n"
    "a status.json containing nothing but a timeout error, forever."
)
HELP_SUPERVISOR_HTTP = (
    "A web UI for the container's internal services (server, backup, updater),\n"
    "plus an XML-RPC API. Useful for poking at a stuck service.\n"
    "It has no TLS and the password sits in plain text — keep it on your LAN.\n"
    "'vh.py backup' and 'vh.py restart' already cover the everyday reasons."
)
HELP_SYSLOG = (
    "Ship the server log to a remote syslog collector. Leave blank for local\n"
    "logging only. Local logging is kept as well, so 'vh.py logs' keeps working."
)
HELP_LOG_FILTER = (
    "Valheim's log is extremely noisy; the container already strips the worst of\n"
    "it. Add your own rules here — each takes a kind and a pattern:\n"
    "  MATCH       the line is exactly this\n"
    "  STARTSWITH  the line begins with this\n"
    "  ENDSWITH    the line ends with this\n"
    "  CONTAINS    this appears anywhere in the line\n"
    "  REGEXP      the line matches this regular expression\n"
    "Every rule needs its own label, because the container reads these variables\n"
    "by prefix: VALHEIM_LOG_FILTER_CONTAINS_<label>. Two rules of the same kind\n"
    "without distinct labels would overwrite each other."
)
HELP_OVERWRITE_WORLD = (
    "A world with this name is already installed in the target instance.\n"
    "Answering yes replaces it with the one you are importing. The world being\n"
    "replaced is NOT backed up by this step — take a backup first if you want one."
)
HELP_SAFETY_COPY = (
    "A Valheim 1.0 server rewrites an older world into the new directory format\n"
    "the first time it opens it, and an older server can never read it again.\n"
    "Yes keeps an untouched copy of the original files inside the instance's data\n"
    "directory, so you can go back to a pre-1.0 server if you need to."
)


# --- discovery ---------------------------------------------------------------
def needs_amd64_platform():
    """True on a host that cannot run this image without emulation.

    The Valheim dedicated server is an x86_64 binary and the image is built for
    linux/amd64 only, so on ARM the container will not start at all unless the
    platform is pinned."""
    return platform.machine().lower() not in ("x86_64", "amd64")


def templates():
    if not TEMPLATES_DIR.exists():
        return []
    return sorted(p.stem for p in TEMPLATES_DIR.glob("*.yml"))


def instances():
    if not INSTANCES_DIR.exists():
        return []
    return sorted(
        p.name for p in INSTANCES_DIR.iterdir()
        if (p / "docker-compose.yml").is_file()
    )


def compose_file(name):
    return INSTANCES_DIR / name / "docker-compose.yml"


def data_dir(name):
    return DATA_DIR / name


def worlds_dir(name):
    return data_dir(name) / "worlds_local"


def container(name):
    return f"vh-{name}"


def running_instances():
    """Names of our instances whose container is currently running.

    Returns an empty set when Docker isn't reachable, so listing still works on
    a machine where the daemon happens to be stopped."""
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return set()
    names = {line.strip() for line in out.splitlines() if line.strip()}
    return {n for n in instances() if container(n) in names}


# --- helpers -----------------------------------------------------------------
def run(cmd):
    print("+ " + " ".join(cmd))
    return subprocess.run(cmd).returncode


def run_quiet(cmd):
    """Run a command, capturing output. Returns (returncode, stdout, stderr)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError as e:
        return 127, "", str(e)


def compose_cmd(name, *args):
    cmd = list(COMPOSE)
    if ENV_FILE.is_file():
        cmd += ["--env-file", str(ENV_FILE)]
    cmd += ["-f", str(compose_file(name)), "-p", name, *args]
    return cmd


def die(msg):
    print("error: " + msg, file=sys.stderr)
    sys.exit(1)


def require_instance(name):
    if not compose_file(name).is_file():
        die(f"no instance named '{name}'. Create one:  python vh.py create"
            f"   (or: python vh.py new {name})")


def require_running(name, what):
    """Guard for the operations commands. Returns True when the container is up."""
    if name in running_instances():
        return True
    if not _docker_available():
        print(f"Docker is not reachable, so '{name}' cannot be running.")
        print("Start Docker, then try again.")
        return False
    print(f"'{name}' is not running, so there is nothing to {what}.")
    print(f"Start it first:  python vh.py up {name}")
    return False


def instance_env(name):
    """The live (uncommented) environment variables of an instance's compose file.

    A deliberately small reader — enough to answer "is STATUS_HTTP on?" without
    dragging in a YAML parser. Commented-out lines are options, not settings, so
    they are ignored on purpose."""
    env = {}
    in_env = False
    for line in compose_file(name).read_text().splitlines():
        if re.match(r"^\s{4}environment:\s*$", line):
            in_env = True
            continue
        if in_env:
            if re.match(r"^\s{0,4}\S", line):      # dedented back out of the block
                in_env = False
                continue
            m = re.match(r"^\s{6}([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
            if m:
                env[m.group(1)] = _unquote(m.group(2))
    return env


def _unquote(raw):
    raw = raw.strip()
    if raw.startswith('"'):
        end = raw.rfind('"')
        return raw[1:end].replace('\\"', '"').replace("\\\\", "\\")
    if raw.startswith("'"):
        end = raw.rfind("'")
        return raw[1:end].replace("''", "'")
    return raw.split("#", 1)[0].strip()


def set_env(name, key, value):
    """Set (or add) a live environment variable in an instance's compose file."""
    path = compose_file(name)
    lines = path.read_text().splitlines(keepends=True)
    pattern = re.compile(r"^(\s{6})" + re.escape(key) + r":\s")
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = f'      {key}: {_yaml_scalar(value)}\n'
            path.write_text("".join(lines))
            return
    for i, line in enumerate(lines):
        if re.match(r"^\s{4}environment:\s*$", line):
            lines.insert(i + 1, f'      {key}: {_yaml_scalar(value)}\n')
            path.write_text("".join(lines))
            return
    die(f"{path} has no 'environment:' block to write {key} into")


def scaffold_content(template_text, name):
    """Strip template-only comment lines and replace the placeholder.

    Lines between a pair of "template-only" marker comments (see
    templates/valheim.yml) are scaffolding instructions meant only for the
    pristine blueprint; they're dropped so a scaffolded instance never says
    "template" about itself."""
    result_lines = []
    skip = False
    for line in template_text.splitlines(keepends=True):
        if "template-only" in line.lower():
            skip = not skip
            continue
        if skip:
            continue
        # On an ARM host the image cannot start at all without this, so make it
        # a real setting rather than a comment the reader has to find.
        if needs_amd64_platform() and line.strip() == "# platform: linux/amd64":
            result_lines.append("    platform: linux/amd64\n")
            continue
        result_lines.append(line.replace(PLACEHOLDER, name))
    return "".join(result_lines)


# --- wizard: prompt helpers --------------------------------------------------
class Abort(Exception):
    """User pressed Ctrl-C / Ctrl-D during the wizard."""


def _read(prompt):
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        raise Abort()


def section(title):
    """Print a consistent section divider between groups of questions."""
    bar = "─" * max(4, 40 - len(title))
    print(f"\n── {title} {bar}")


def _show_help(help_text):
    """Print the help block for a '?' request (or a fallback if none was given)."""
    print("\n  " + (help_text or "No extra help for this one.").replace("\n", "\n  ") + "\n")


def ask(prompt, help_text="", default=None, allow_empty=False):
    suffix = f" [{default}]" if default is not None else ""
    while True:
        ans = _read(f"{prompt}{suffix} (?): ").strip()
        if ans == "?":
            _show_help(help_text)
            continue
        if not ans and default is not None:
            return default
        if not ans and allow_empty:
            return ""
        if ans:
            return ans


def ask_int(prompt, help_text="", default=None):
    """Like ask() but requires a non-negative integer; returns it as a string."""
    while True:
        ans = ask(prompt, help_text, default)
        if str(ans).isdigit():
            return str(ans)
        print("  (enter a whole number)")


def ask_yes_no(prompt, help_text="", default=True):
    choices = "Y/n" if default else "y/N"
    while True:
        ans = _read(f"{prompt} [{choices}] (?): ").strip().lower()
        if ans == "?":
            _show_help(help_text)
            continue
        if not ans:
            return default
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("  (answer y or n)")


def ask_choice(prompt, options, help_text="", default=None):
    """options: list of (value, label). Returns the chosen value."""
    while True:
        print(prompt + " (?)")
        for i, (val, label) in enumerate(options, 1):
            mark = "  (default)" if val == default else ""
            print(f"  {i}) {label}{mark}")
        ans = _read("> ").strip().lower()
        if ans == "?":
            _show_help(help_text)
            continue
        if not ans and default is not None:
            return default
        if ans.isdigit():
            idx = int(ans) - 1
            if 0 <= idx < len(options):
                return options[idx][0]
        for val, label in options:
            if val is not None and ans == str(val).lower():
                return val
        print("  (pick a number or a name)")


def ask_cron(prompt, help_text, default):
    """A five-field cron expression, or "off" to disable the schedule.

    Enter keeps the default, so disabling needs a word of its own — otherwise
    there would be no way to say "never" at a prompt that has a default."""
    while True:
        ans = ask(prompt, help_text, default)
        if ans.lower() in ("off", "none", "never", "-"):
            return ""
        if len(ans.split()) == 5:
            return ans
        print("  (cron needs five fields: minute hour day month weekday —"
              " or 'off' to disable this schedule)")


def ask_steam_ids(prompt, help_text):
    """Space-separated SteamID64s. Returns the cleaned string, possibly empty."""
    while True:
        ans = ask(prompt, help_text, default="", allow_empty=True)
        if not ans:
            return ""
        ids = ans.replace(",", " ").split()
        bad = [i for i in ids if not (i.isdigit() and len(i) == 17)]
        if bad:
            print(f"  (not SteamID64s: {' '.join(bad)} — expected 17 digits each)")
            continue
        return " ".join(ids)


# --- wizard: name validation -------------------------------------------------
def _name_problem(name):
    """Why this instance name can't be used, or None if it's fine."""
    if not name:
        return "the name cannot be empty."
    if not all(c.isalnum() or c in "-_" for c in name):
        return "use only letters, digits, '-' or '_'."
    if name in RESERVED_NAMES:
        return (f"'{name}' is reserved — that directory holds the shared Valheim\n"
                "  download that every instance mounts. Pick another name.")
    if compose_file(name).is_file():
        return f"instance '{name}' already exists — pick another."
    return None


def _ask_new_name():
    while True:
        name = ask("Instance name", HELP_NAME)
        problem = _name_problem(name)
        if problem:
            print("  " + problem)
            continue
        return name


# --- wizard: clean compose generator -----------------------------------------
def _yaml_scalar(value):
    """Quote a value for YAML, and escape '$' the way compose expects.

    docker compose expands $VAR in compose files before the container sees it,
    so a literal dollar has to be written '$$'. Values arrive here as the string
    we want the SERVER to receive; the doubling happens in one place, here."""
    v = str(value).replace("$", "$$")
    if '"' in v and "'" not in v:
        return "'" + v + "'"
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _block(key, items):
    """A YAML `key: |` literal block with each item indented under it.

    Nothing in Valheim's surface is list-shaped today, but the generator keeps
    the directive kind so a multi-line value has an obvious home — and so this
    file reads the same way as the sibling repo's mc.py."""
    out = [f"      {key}: |"]
    out += [f"        {it}" for it in items]
    return out


def build_compose(a):
    """Assemble a clean docker-compose.yml from the wizard's answers.

    `a["env"]` is an ordered list of directives, each ("scalar", KEY, value),
    ("block", KEY, [items]) or ("comment", text); only what the wizard added is
    emitted, so the output stays minimal. A "comment" renders as real YAML
    comment line(s) OUTSIDE any block — never inside a `KEY: |` list, where a
    '#' line would be read as a literal entry."""
    name = a["name"]
    lines = [
        f"# {name} — Valheim dedicated server",
        "# Generated by vh.py create. Only the settings you chose appear here;",
        "# everything else is at the container's default. See templates/valheim.yml",
        "# for the full annotated option reference.",
        "services:",
        "  valheim:",
        f"    image: {IMAGE}",
        f"    container_name: vh-{name}",
        "    restart: unless-stopped",
    ]
    if needs_amd64_platform():
        # x86_64-only image on an ARM host: without this it will not start.
        lines.append("    platform: linux/amd64")
    lines += [
        "    cap_add:",
        "      - sys_nice",
        "    stop_grace_period: 2m",
        "    ports:",
    ]
    lines += [f'      - "{p}"' for p in a["ports"]]
    lines.append("    environment:")
    for directive in a["env"]:
        kind = directive[0]
        if kind == "scalar":
            _, key, value = directive
            lines.append(f"      {key}: {_yaml_scalar(value)}")
        elif kind == "comment":
            _, text = directive
            lines += [f"      # {ln}" if ln else "      #" for ln in text.split("\n")]
        else:  # ("block", KEY, [items]) — items are real entries only, never '#'
            _, key, items = directive
            lines += _block(key, items)
    lines += [
        "    volumes:",
        f"      - ../../data/{name}:/config",
        "      - ../../server:/opt/valheim",
    ]
    return "\n".join(lines) + "\n"


def _print_summary(a):
    section("Summary")
    print(f"  {'instance':<28} {a['name']}")
    print(f"  {'ports':<28} {', '.join(a['ports'])}")
    for d in a["env"]:
        if d[0] == "scalar":
            value = d[2]
            if len(str(value)) > 46:
                value = str(value)[:43] + "..."
            print(f"  {d[1]:<28} {value}")
        elif d[0] == "block":
            print(f"  {d[1]:<28} {', '.join(d[2]) or '(none)'}")
        # "comment" directives are guidance for the file, not settings — skip.
    print(f"  {'file':<28} {compose_file(a['name'])}")
    print(f"  {'world data':<28} {data_dir(a['name'])}")


# --- wizard: advanced topics -------------------------------------------------
def _topic_gameplay(scalar):
    """Difficulty preset, individual modifiers and setkeys → one SERVER_ARGS.

    Collected first, serialised afterwards: the server applies arguments left to
    right and a -preset RESETS every modifier before it, so a preset written
    after a modifier silently throws that modifier away. Building the string in
    a fixed order — preset, modifiers, setkeys — makes that impossible."""
    section("Gameplay")
    preset = ask_choice(
        "Difficulty preset?",
        [(None, "none — leave the world at standard settings")]
        + [(p, p) for p in PRESETS],
        HELP_PRESET, default=None,
    )
    modifiers = []
    if ask_yes_no("Adjust individual modifiers?", HELP_MODIFIERS, default=False):
        for cat, values in MODIFIERS.items():
            choice = ask_choice(
                f"  {cat}?",
                [(None, "standard — leave it alone")] + [(v, v) for v in values],
                HELP_MODIFIERS, default=None,
            )
            if choice:
                modifiers.append((cat, choice))
    setkeys = []
    if ask_yes_no("Turn on any of the on/off switches?", HELP_SETKEYS, default=False):
        for key, what in SETKEYS.items():
            if ask_yes_no(f"  {key} — {what}?", HELP_SETKEYS, default=False):
                setkeys.append(key)

    args = []
    if preset:                                   # 1. preset resets everything
        args.append(f"-preset {preset}")
    for cat, value in modifiers:                 # 2. then the individual dials
        args.append(f"-modifier {cat} {value}")
    for key in setkeys:                          # 3. then the switches
        args.append(f"-setkey {key}")
    if args:
        scalar("SERVER_ARGS", " ".join(args))


def _topic_access(scalar):
    section("Access control")
    print("  SteamID64s, space separated. Leave any of these empty to skip it.")
    admins = ask_steam_ids("Admins", HELP_ADMINLIST)
    if admins:
        scalar("ADMINLIST_IDS", admins)
    banned = ask_steam_ids("Banned players", HELP_BANNEDLIST)
    if banned:
        scalar("BANNEDLIST_IDS", banned)
    permitted = ask_steam_ids("Whitelist (only these may join)", HELP_PERMITTEDLIST)
    if permitted:
        scalar("PERMITTEDLIST_IDS", permitted)


def _topic_backups(scalar, state):
    section("Backups")
    if not ask_yes_no("Keep periodic world backups?", HELP_BACKUPS, default=True):
        scalar("BACKUPS", "false")
        state["zip"] = True
        return
    print("  (backups are on by default — answer these only to change them)")
    age = ask_int("Delete backups older than (days)", HELP_MAX_AGE, default="3")
    if age != "3":
        scalar("BACKUPS_MAX_AGE", age)
    count = ask_int("Keep at most how many backups (0 = no limit)",
                    HELP_MAX_COUNT, default="0")
    if count != "0":
        scalar("BACKUPS_MAX_COUNT", count)
    zip_on = ask_yes_no("Compress each backup into a .zip?", HELP_BACKUPS_ZIP,
                        default=True)
    state["zip"] = zip_on
    if not zip_on:
        scalar("BACKUPS_ZIP", "false")
    if not ask_yes_no("Back up even when nobody is online?", HELP_BACKUPS_IF_IDLE,
                      default=True):
        scalar("BACKUPS_IF_IDLE", "false")
        grace = ask_int("Keep backing up for how many seconds after the last"
                        " player leaves", HELP_BACKUPS_GRACE, default="3600")
        if grace != "3600":
            scalar("BACKUPS_IDLE_GRACE_PERIOD", grace)


def _topic_schedules(scalar):
    section("Schedules")
    print("  Cron expressions, in the container's time zone.")
    print("  Press Enter to keep the default — defaults are not written to the file.")
    tz = ask("Time zone", HELP_TZ, default="Etc/UTC")
    if tz != "Etc/UTC":
        scalar("TZ", tz)
    for key, help_text in (
        ("BACKUPS_CRON", HELP_CRON),
        ("UPDATE_CRON", HELP_UPDATE_CRON),
        ("RESTART_CRON", HELP_RESTART_CRON),
    ):
        default = CRON_DEFAULTS[key]
        answer = ask_cron(f"{key}", help_text, default)
        if answer != default:
            scalar(key, answer)
    for key in ("UPDATE_IF_IDLE", "RESTART_IF_IDLE"):
        what = "update checks" if key.startswith("UPDATE") else "the daily restart"
        if not ask_yes_no(f"Run {what} only when nobody is connected?",
                          HELP_IF_IDLE, default=True):
            scalar(key, "false")


DISCORD_POST = (
    'curl -sfSL -X POST -H "Content-Type: application/json" '
    '-d "{{\\"username\\":\\"Valheim\\",\\"content\\":\\"{msg}\\"}}" "$DISCORD_WEBHOOK"'
)


def _topic_notifications(scalar, state):
    section("Notifications")
    if not ask_yes_no("Post server events to a Discord channel?", HELP_DISCORD,
                      default=False):
        return
    webhook = ask("Discord webhook URL", HELP_DISCORD)
    scalar("DISCORD_WEBHOOK", webhook)
    print()
    hooks = []
    if ask_yes_no("  Announce when the server is up?", HELP_HOOK_PICK, default=True):
        hooks.append(("POST_SERVER_LISTENING_HOOK",
                      DISCORD_POST.format(msg="$SERVER_NAME is up")))
    if ask_yes_no("  Warn before a scheduled restart?", HELP_HOOK_PICK, default=True):
        hooks.append(("PRE_RESTART_HOOK",
                      DISCORD_POST.format(msg="$SERVER_NAME restarts in one minute")
                      + " && sleep 60"))
    if ask_yes_no("  Report each completed backup?", HELP_HOOK_PICK, default=False):
        if not state.get("zip", True):
            print("  ! You turned .zip compression off, so a backup is a DIRECTORY,")
            print("    not a file. This hook only announces it — but any hook you")
            print("    add later to copy @BACKUP_FILE@ elsewhere must copy with -r.")
        hooks.append(("POST_BACKUP_HOOK",
                      DISCORD_POST.format(msg="Backup complete: @BACKUP_FILE@")))
    for key, command in hooks:
        scalar(key, command)
    if ask_yes_no("  Announce each player who joins?", HELP_HOOK_PICK, default=False):
        # A log-filter TRIGGER rather than a lifecycle hook: the filter matches
        # the line, and the ON_ variable consumes it on stdin instead of dropping it.
        scalar("VALHEIM_LOG_FILTER_CONTAINS_Spawned", "Got character ZDOID from")
        scalar("ON_VALHEIM_LOG_FILTER_CONTAINS_Spawned",
               "{ read l; l=${l//*ZDOID from /}; l=${l// :*/}; "
               + DISCORD_POST.format(msg="Player $l spawned into the world") + "; }")


def _topic_monitoring(scalar, ports, state):
    section("Monitoring")
    if ask_yes_no("Publish a status.json web page (player count, version)?",
                  HELP_STATUS_HTTP, default=False):
        if not state.get("public", True):
            print("  ! This server is NOT public, so it does not answer Steam")
            print("    queries and status.json will only ever contain a timeout")
            print("    error. Set the server public if you want live status.")
        scalar("STATUS_HTTP", "true")
        host_port = ask_int("  Host port to serve it on", HELP_STATUS_HTTP,
                            default="8080")
        ports.append(f"{host_port}:80/tcp")
    if ask_yes_no("Enable the supervisor web UI?", HELP_SUPERVISOR_HTTP,
                  default=False):
        scalar("SUPERVISOR_HTTP", "true")
        user = ask("  Username", HELP_SUPERVISOR_HTTP, default="admin")
        if user != "admin":
            scalar("SUPERVISOR_HTTP_USER", user)
        scalar("SUPERVISOR_HTTP_PASS", ask("  Password", HELP_SUPERVISOR_HTTP))
        host_port = ask_int("  Host port", HELP_SUPERVISOR_HTTP, default="9001")
        ports.append(f"{host_port}:9001/tcp")
    syslog = ask("Remote syslog host (blank for local logging only)",
                 HELP_SYSLOG, default="", allow_empty=True)
    if syslog:
        scalar("SYSLOG_REMOTE_HOST", syslog)
        port = ask_int("  Remote syslog port", HELP_SYSLOG, default="514")
        if port != "514":
            scalar("SYSLOG_REMOTE_PORT", port)


def _topic_log_filters(scalar):
    section("Log filters")
    if not ask_yes_no("Add your own log filters?", HELP_LOG_FILTER, default=False):
        return
    used = set()
    n = 0
    while True:
        n += 1
        kind = ask_choice(
            f"Filter {n} — what kind?",
            [(k, f"{k.lower()}") for k in LOG_FILTER_KINDS],
            HELP_LOG_FILTER, default="CONTAINS",
        )
        pattern = ask("  Pattern", HELP_LOG_FILTER)
        # The container reads these variables BY PREFIX, so two rules of the same
        # kind must differ in their suffix or the second silently replaces the first.
        while True:
            label = ask("  Label for this rule (letters/digits)", HELP_LOG_FILTER,
                        default=f"Rule{n}")
            label = re.sub(r"[^A-Za-z0-9]", "", label)
            key = f"VALHEIM_LOG_FILTER_{kind}_{label}" if label \
                else f"VALHEIM_LOG_FILTER_{kind}"
            if key in used:
                print(f"  ({key} is already taken by an earlier rule — pick"
                      " another label)")
                continue
            break
        used.add(key)
        scalar(key, pattern)
        if not ask_yes_no("  Another filter?", HELP_LOG_FILTER, default=False):
            return


# --- wizard: the guided flow -------------------------------------------------
def _wizard():
    print("=== New Valheim server — guided setup ===")
    print("Press Enter to accept the [default]; type ? at any prompt for help.")

    env = []
    ports = ["2456-2457:2456-2457/udp"]
    state = {}

    def scalar(key, value):
        env.append(("scalar", key, value))

    section("Essentials")
    name = _ask_new_name()
    server_name = ask("Name shown in the server browser", HELP_SERVER_NAME,
                      default=name)
    world_name = ask("World name", HELP_WORLD_NAME, default=name)
    while True:
        password = ask("Password", HELP_PASSWORD)
        if len(password) < 5:
            print("  the server refuses to start with a password under 5"
                  " characters — pick a longer one.")
            continue
        if password in server_name or password in world_name:
            print("  the password may not appear inside the server name or the"
                  " world name — pick another.")
            continue
        break
    public = ask_yes_no("List the server publicly?", HELP_PUBLIC, default=True)
    state["public"] = public
    crossplay = ask_yes_no("Enable crossplay (non-Steam players)?", HELP_CROSSPLAY,
                           default=False)

    scalar("SERVER_NAME", server_name)
    scalar("WORLD_NAME", world_name)
    scalar("SERVER_PASS", password)
    if not public:
        scalar("SERVER_PUBLIC", "false")
    if crossplay:
        scalar("CROSSPLAY", "true")
        ports.append("2458:2458/udp")     # PlayFab backend, and mod RPC

    section("Advanced")
    if ask_yes_no("Configure advanced settings?", HELP_ADVANCED, default=False):
        if ask_yes_no("Gameplay — difficulty, resources, raids, portals?",
                      HELP_PRESET, default=False):
            _topic_gameplay(scalar)
        if ask_yes_no("Access control — admins, bans, whitelist?",
                      HELP_ADMINLIST, default=False):
            _topic_access(scalar)
        if ask_yes_no("Backups — retention, compression, idle behaviour?",
                      HELP_BACKUPS, default=False):
            _topic_backups(scalar, state)
        if ask_yes_no("Schedules — backup, update and restart timing?",
                      HELP_CRON, default=False):
            _topic_schedules(scalar)
        if ask_yes_no("Notifications — post events to Discord?",
                      HELP_DISCORD, default=False):
            _topic_notifications(scalar, state)
        if ask_yes_no("Monitoring — status page, supervisor UI, syslog?",
                      HELP_STATUS_HTTP, default=False):
            _topic_monitoring(scalar, ports, state)
        if ask_yes_no("Log filters — quieten or react to log lines?",
                      HELP_LOG_FILTER, default=False):
            _topic_log_filters(scalar)

    a = {"name": name, "env": env, "ports": ports, "public": public}
    _print_summary(a)
    if not ask_yes_no("Write this instance?", "", default=True):
        return None
    return a


# --- world import ------------------------------------------------------------
def detect_world(path):
    """Classify a path as a Valheim world.

    Returns (kind, world_name, files) where kind is "1.0" (a directory of chunk
    files) or "pre-1.0" (a .db/.fwl pair), or (None, None, None)."""
    path = Path(path).expanduser()
    if not path.exists():
        return None, None, None
    if path.is_dir():
        entries = list(path.iterdir())
        looks_like_world = any(
            e.name.startswith("_main.") or e.suffix in (".fwl", ".db")
            for e in entries
        )
        if looks_like_world:
            return "1.0", path.name, [path]
        return None, None, None
    # A file: accept either half of the pair and require both to be present.
    if path.suffix in (".db", ".fwl"):
        stem = path.with_suffix("")
        db, fwl = Path(f"{stem}.db"), Path(f"{stem}.fwl")
        if db.is_file() and fwl.is_file():
            return "pre-1.0", path.stem, [db, fwl]
        missing = fwl if db.is_file() else db
        print(f"  {path.name} is missing its partner file: {missing.name}")
        return None, None, None
    return None, None, None


# --- commands ----------------------------------------------------------------
def cmd_ls(_args=None):
    print("Template (blueprint):")
    for t in templates():
        print(f"  - {t}")
    running = running_instances()
    docker_up = _docker_available()
    insts = instances()
    print("\nInstances (your servers):")
    if not insts:
        print("  (none yet — create one with:  python vh.py create)")
    for i in insts:
        if not docker_up:
            state = "unknown — Docker not reachable"
        else:
            state = "running" if i in running else "stopped"
        print(f"  - {i:<24} [{state}]")
    return 0


def _docker_available():
    rc, _, _ = run_quiet(["docker", "ps", "--quiet"])
    return rc == 0


def cmd_new(args):
    if len(args) != 1:
        die("usage: python vh.py new <name>")
    name = args[0]
    problem = _name_problem(name)
    if problem:
        die(problem.rstrip("."))
    src = TEMPLATES_DIR / "valheim.yml"
    if not src.is_file():
        die(f"missing template: {src}")
    dest = compose_file(name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(scaffold_content(src.read_text(), name))
    print(f"Created instance '{name}' from the template:")
    print(f"  {dest}")
    print("\nNext:")
    print(f"  1. edit {dest} — at minimum set SERVER_PASS (5+ characters)")
    print(f"  2. python vh.py up {name}")
    return 0


def cmd_create(_args=None):
    """Guided wizard → a clean instance compose file assembled from your answers."""
    try:
        a = _wizard()
    except Abort:
        print("\nCancelled — nothing was created.")
        return 1
    if a is None:                       # user declined at the summary
        print("Cancelled — nothing was created.")
        return 1
    dest = compose_file(a["name"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(build_compose(a))
    print(f"\nCreated instance '{a['name']}':")
    print(f"  {dest}")
    print("\nNext:")
    print(f"  1. review {dest}")
    print(f"  2. python vh.py up {a['name']}")
    print("\nThe first start downloads the Valheim server (~1 GB) into"
          f" {SERVER_DIR}.")
    print("  Follow it with:  python vh.py logs " + a["name"])
    if not a["public"]:
        print("\nThis server is unlisted — players join with 'Join IP' in-game.")
    return 0


def cmd_up(args):
    if len(args) != 1:
        die("usage: python vh.py up <name>")
    name = args[0]
    require_instance(name)
    # One host, one set of UDP ports, one shared server download — stop the rest.
    for other in running_instances():
        if other != name:
            print(f"Stopping '{other}' first (shared ports and server directory)...")
            run(compose_cmd(other, "stop"))
    if needs_amd64_platform():
        print("! This machine is " + platform.machine() + ", and the Valheim")
        print("  dedicated server is an x86_64 binary. The container will start")
        print("  under emulation, but SteamCMD segfaults there and the game")
        print("  download never completes — the server will retry forever.")
        print("  Run the server on an x86_64 host. See README.md.\n")
    data_dir(name).mkdir(parents=True, exist_ok=True)
    SERVER_DIR.mkdir(parents=True, exist_ok=True)
    return run(compose_cmd(name, "up", "-d"))


def cmd_down(args):
    if len(args) != 1:
        die("usage: python vh.py down <name>")
    name = args[0]
    require_instance(name)
    # compose honours stop_grace_period (2m in every generated instance), which
    # is what gives the server time to write the world before it is killed.
    print("Stopping — the server needs up to two minutes to save the world.")
    return run(compose_cmd(name, "down"))


def cmd_logs(args):
    if len(args) != 1:
        die("usage: python vh.py logs <name>")
    name = args[0]
    require_instance(name)
    try:
        return run(["docker", "logs", "-f", container(name)])
    except KeyboardInterrupt:
        print()
        return 0


def cmd_backup(args):
    if len(args) != 1:
        die("usage: python vh.py backup <name>")
    name = args[0]
    require_instance(name)
    if not require_running(name, "back up"):
        return 1
    # Restart, not SIGHUP: with BACKUPS_IF_IDLE=false a HUP only produces a
    # backup when there has been recent player activity, so "force a backup"
    # would quietly do nothing on an idle server. Restarting always backs up.
    rc = run(["docker", "exec", container(name),
              "supervisorctl", "restart", "valheim-backup"])
    if rc != 0:
        print("The backup service did not restart cleanly — check the log:")
        print(f"  python vh.py logs {name}")
        return rc
    env = instance_env(name)
    inside = env.get("BACKUPS_DIRECTORY", DEFAULT_BACKUPS_DIRECTORY)
    print("\nBackup started. It is written to:")
    if inside.startswith("/config/"):
        print(f"  {data_dir(name) / inside[len('/config/'):]}")
    else:
        print(f"  {inside}  (inside the container)")
    if env.get("BACKUPS", "true") == "false":
        print("  note: BACKUPS is set to false, so no further backups are"
              " scheduled after this one.")
    return 0


def cmd_restart(args):
    if len(args) != 1:
        die("usage: python vh.py restart <name>")
    name = args[0]
    require_instance(name)
    if not require_running(name, "restart"):
        print("(that would recreate the container and re-run the update check;"
              " this command only restarts the game process)")
        return 1
    print("Restarting the game process inside the running container.")
    print("The container itself stays up — no image pull, no update check.")
    rc = run(["docker", "exec", container(name),
              "supervisorctl", "restart", "valheim-server"])
    if rc == 0:
        print(f"\nDone. Watch it come back with:  python vh.py logs {name}")
    return rc


def cmd_status(args):
    if len(args) != 1:
        die("usage: python vh.py status <name>")
    name = args[0]
    require_instance(name)
    if name not in running_instances():
        if not _docker_available():
            print(f"Docker is not reachable, so '{name}' cannot be running.")
            print("Start Docker, then try again.")
            return 0
        print(f"'{name}' is not running.")
        print(f"Start it with:  python vh.py up {name}")
        return 0

    print(f"Instance '{name}' — container {container(name)} is up.\n")

    rc, out, _ = run_quiet(["docker", "exec", container(name),
                            "supervisorctl", "status"])
    if rc in (0, 3) and out.strip():          # 3 = "some services not running"
        print("Services:")
        for line in out.splitlines():
            print("  " + line.rstrip())
    else:
        print("Services: could not query the container's supervisor.")

    rc, out, _ = run_quiet(["docker", "exec", container(name),
                            "cat", SERVER_STATUS_FILE])
    if rc == 0 and out.strip():
        print(f"\nServer state: {out.strip()}")

    env = instance_env(name)
    htdocs = env.get("STATUS_HTTP_HTDOCS", DEFAULT_STATUS_HTDOCS)
    rc, out, _ = run_quiet(["docker", "exec", container(name),
                            "cat", f"{htdocs}/status.json"])
    live = None
    if rc == 0:
        try:
            live = json.loads(out)
        except ValueError:
            live = None

    if live and not live.get("error"):
        print("\nLive:")
        print(f"  {'server name':<16} {live.get('server_name', '?')}")
        print(f"  {'players online':<16} {live.get('player_count', '?')}")
        print(f"  {'version':<16} {live.get('keywords', '?')}")
        print(f"  {'game port':<16} {live.get('port', '?')}")
        print(f"  {'password':<16} "
              f"{'yes' if live.get('password_protected') else 'no'}")
        print(f"  {'updated':<16} {live.get('last_status_update', '?')}")
        return 0

    # No live details. Say which setting is in the way rather than erroring.
    print("\nLive details (player count, version) are not available.")
    missing = []
    if env.get("STATUS_HTTP", "false") != "true":
        missing.append("STATUS_HTTP: \"true\"  — runs the status collector")
    if env.get("SERVER_PUBLIC", "true") == "false":
        missing.append("SERVER_PUBLIC: \"true\" — private servers do not answer"
                       " Steam queries, which is where the data comes from")
    if missing:
        print("They need these settings in " + str(compose_file(name)) + ":")
        for m in missing:
            print("  " + m)
    elif live and live.get("error"):
        print(f"  The status collector reported: {live['error']}")
        print("  That is normal for the first minute or two after a start.")
    else:
        print("  The status file has not been written yet — it appears about"
              " 10 seconds after the server starts listening.")
    return 0


def cmd_import(args):
    if len(args) != 2:
        die("usage: python vh.py import <name> <path-to-world>")
    name, src_path = args
    require_instance(name)

    kind, world, sources = detect_world(src_path)
    if kind is None:
        die(f"'{src_path}' does not look like a Valheim world.\n"
            "  Expected either a Valheim 1.0 world DIRECTORY, or a pre-1.0\n"
            "  '<world>.db' file with its '<world>.fwl' beside it.\n"
            "  Worlds live in worlds_local/ — on Windows that is\n"
            "  %USERPROFILE%\\AppData\\LocalLow\\IronGate\\Valheim\\worlds_local")

    print(f"Detected a {kind} world named '{world}'.")
    target_dir = worlds_dir(name)
    if kind == "1.0":
        targets = [target_dir / world]
    else:
        targets = [target_dir / f"{world}.db", target_dir / f"{world}.fwl"]

    existing = [t for t in targets if t.exists()]
    if existing:
        print(f"\n'{name}' already has a world called '{world}':")
        for t in existing:
            print(f"  {t}")
        try:
            if not ask_yes_no("Replace it?", HELP_OVERWRITE_WORLD, default=False):
                print("Nothing was imported.")
                return 1
        except Abort:
            print("Nothing was imported.")
            return 1

    if kind == "pre-1.0":
        print("\n  ⚠ This world predates Valheim 1.0. The first time a 1.0 server")
        print("    opens it, it is rewritten into the new directory format, and")
        print("    older servers can never read it again. This is one-way.")
        try:
            if ask_yes_no("  Keep an untouched copy of the original first?",
                          HELP_SAFETY_COPY, default=True):
                safety = data_dir(name) / "pre-1.0-originals" / world
                safety.mkdir(parents=True, exist_ok=True)
                for s in sources:
                    shutil.copy2(s, safety / s.name)
                print(f"    Safety copy kept at: {safety}")
        except Abort:
            print("\nNothing was imported.")
            return 1

    target_dir.mkdir(parents=True, exist_ok=True)
    for t in existing:
        if t.is_dir():
            shutil.rmtree(t)
        else:
            t.unlink()
    for s in sources:
        dest = target_dir / s.name
        if s.is_dir():
            shutil.copytree(s, dest)
        else:
            shutil.copy2(s, dest)

    set_env(name, "WORLD_NAME", world)
    print(f"\nImported into {target_dir}")
    print(f"Set WORLD_NAME to '{world}' in {compose_file(name)}")
    print(f"\nStart it with:  python vh.py up {name}")
    return 0


COMMANDS = {
    "ls": cmd_ls,
    "create": cmd_create,
    "new": cmd_new,
    "up": cmd_up,
    "down": cmd_down,
    "logs": cmd_logs,
    "backup": cmd_backup,
    "restart": cmd_restart,
    "status": cmd_status,
    "import": cmd_import,
}


# --- interactive menu --------------------------------------------------------
def interactive():
    print("=== Valheim server manager ===")
    while True:
        cmd_ls()
        print("\nCommands: create | new <name> | up <name> | down <name> | "
              "logs <name>")
        print("          backup <name> | restart <name> | status <name> | "
              "import <name> <path>")
        print("          ls | quit")
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in ("quit", "q", "exit"):
            return 0
        parts = line.split()
        verb, rest = parts[0], parts[1:]
        if verb not in COMMANDS:
            print(f"unknown command: {verb}")
            continue
        try:
            COMMANDS[verb](rest)
        except SystemExit as e:     # let die() report without killing the menu
            if e.code:
                print(e.code if isinstance(e.code, str) else "", file=sys.stderr)
        except Abort:
            print("\nCancelled.")
        print()


def main(argv):
    if not argv:
        return interactive()
    verb, rest = argv[0], argv[1:]
    if verb in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if verb not in COMMANDS:
        die(f"unknown command '{verb}'. Run 'python vh.py --help'.")
    return COMMANDS[verb](rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
