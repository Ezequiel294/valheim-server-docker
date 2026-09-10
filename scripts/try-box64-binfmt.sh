#!/usr/bin/env bash
# try-box64-binfmt.sh — can this ARM Linux host run the stock amd64 Valheim
# image under box64 instead of QEMU?
#
# Run this ON THE ARM HOST (e.g. a Raspberry Pi 5), not on your laptop.
#
# It works in stages and stops at the first failure, so the output tells you
# which gate broke rather than just "it didn't work". Nothing here is
# irreversible: `sudo ./try-box64-binfmt.sh --undo` removes what it registered.
#
# What it changes:
#   - installs build dependencies via apt (git, cmake, build-essential)
#   - builds box64 from source into /usr/local/bin/box64-static
#   - registers that binary as the kernel's x86_64 and i386 handler
#     (/etc/binfmt.d/box64*.conf)
#   - disables an existing qemu-x86_64 handler if one is registered, because
#     the two would otherwise fight over the same executable format
set -uo pipefail

IMAGE="ghcr.io/community-valheim-tools/valheim-server:latest"
BOX64_BIN="/usr/local/bin/box64-static"
SRC="${SRC:-/usr/local/src/box64}"

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mPASS\033[0m  %s\n' "$*"; }
bad()  { printf '   \033[31mFAIL\033[0m  %s\n' "$*"; }
note() { printf '         %s\n' "$*"; }
die()  { bad "$1"; shift; for l in "$@"; do note "$l"; done; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run this with sudo" "  sudo $0"

# --- undo --------------------------------------------------------------------
if [ "${1:-}" = "--undo" ]; then
    say "Undoing"
    for n in box64 box64-i386; do
        [ -e "/proc/sys/fs/binfmt_misc/$n" ] && echo -1 > "/proc/sys/fs/binfmt_misc/$n" && note "unregistered $n"
        rm -f "/etc/binfmt.d/$n.conf"
    done
    [ -f /etc/binfmt.d/qemu-x86_64.conf.disabled-by-box64-test ] &&
        mv /etc/binfmt.d/qemu-x86_64.conf{.disabled-by-box64-test,} && note "restored qemu handler"
    systemctl restart systemd-binfmt 2>/dev/null
    ok "removed. $BOX64_BIN and $SRC were left in place; delete them if you like."
    exit 0
fi

# --- stage 1: preflight ------------------------------------------------------
say "Stage 1 — preflight"

arch=$(uname -m)
[ "$arch" = "aarch64" ] || die "this host is $arch, not aarch64" \
    "This script is for 64-bit ARM Linux. On x86_64 you need none of it."
ok "architecture is aarch64"

pagesize=$(getconf PAGESIZE)
if [ "$pagesize" != "4096" ]; then
    die "page size is $pagesize, box64 needs 4096" \
        "The Pi 5 defaults to a 16K-page kernel. Switch it:" \
        "    echo 'kernel=kernel8.img' | sudo tee -a /boot/firmware/config.txt" \
        "    sudo reboot" \
        "Then run this script again. This is the most common reason box64 fails on a Pi 5."
fi
ok "page size is 4096"

command -v docker >/dev/null || die "docker is not installed"
docker info >/dev/null 2>&1 || die "the docker daemon is not reachable"
ok "docker is available"

# integer maths only — bc is not installed yet at this point
memkb=$(awk '/MemTotal/{print $2}' /proc/meminfo)
memgb=$(( memkb / 1048576 ))
if [ "$memgb" -lt 7 ]; then
    note "warning: ~${memgb}GB RAM. Valheim idles near 2.8GB; 8GB+ is recommended."
else
    ok "~${memgb}GB RAM"
fi

# --- stage 2: build box64 ----------------------------------------------------
say "Stage 2 — build a static box64 (with 32-bit support)"

if [ -x "$BOX64_BIN" ]; then
    ok "already built at $BOX64_BIN"
else
    note "installing build dependencies..."
    apt-get update -qq && apt-get install -y -qq git cmake build-essential python3 \
        || die "could not install build dependencies"

    [ -d "$SRC" ] || git clone --depth 1 https://github.com/ptitSeb/box64 "$SRC" \
        || die "could not clone box64"
    cd "$SRC" && git pull -q 2>/dev/null
    rm -rf build && mkdir -p build && cd build

    # STATICBUILD matters: box64 is an arm64 binary, and inside an amd64
    # container its arm64 shared libraries do not exist. A dynamic build fails
    # there for exactly the reason dynamically-linked qemu does.
    # BOX32 lets box64 handle 32-bit x86 too, so SteamCMD needs no box86.
    note "configuring (RPI5ARM64, BOX32, STATICBUILD)..."
    if ! cmake .. -DRPI5ARM64=1 -DBOX32=ON -DBOX32_BINFMT=ON -DSTATICBUILD=ON \
                  -DCMAKE_BUILD_TYPE=RelWithDebInfo > /tmp/box64-cmake.log 2>&1; then
        note "that combination was rejected; retrying without STATICBUILD..."
        note "(a dynamic handler often cannot work inside a container — if the"
        note " later stages fail on missing libraries, this is why)"
        cmake .. -DRPI5ARM64=1 -DBOX32=ON -DBOX32_BINFMT=ON \
                 -DCMAKE_BUILD_TYPE=RelWithDebInfo > /tmp/box64-cmake.log 2>&1 \
            || die "cmake failed — see /tmp/box64-cmake.log"
    fi

    note "compiling (a few minutes)..."
    make -j"$(nproc)" > /tmp/box64-make.log 2>&1 || die "build failed — see /tmp/box64-make.log"
    install -m755 box64 "$BOX64_BIN" || die "could not install box64"
    ok "built $BOX64_BIN"
fi

if file "$BOX64_BIN" | grep -q "statically linked"; then
    ok "handler is statically linked"
else
    note "warning: handler is dynamically linked — it may not resolve inside a container"
fi

# --- stage 3: register with binfmt_misc --------------------------------------
say "Stage 3 — register box64 as the x86 handler"

if [ -f /etc/binfmt.d/qemu-x86_64.conf ]; then
    mv /etc/binfmt.d/qemu-x86_64.conf /etc/binfmt.d/qemu-x86_64.conf.disabled-by-box64-test
    note "moved the existing qemu-x86_64 handler aside (--undo restores it)"
fi
for n in qemu-x86_64 qemu-i386; do
    [ -e "/proc/sys/fs/binfmt_misc/$n" ] && echo -1 > "/proc/sys/fs/binfmt_misc/$n" && note "unregistered $n"
done

# The trailing :F is the point of the exercise — "fix binary" pins the
# interpreter at registration time so it still resolves inside a container's
# mount namespace.
cat > /etc/binfmt.d/box64.conf <<CONF
:box64:M::\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x3e\x00:\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\xff\xff\xff\xff\xff\xfe\xff\xff\xff:$BOX64_BIN:F
CONF
cat > /etc/binfmt.d/box64-i386.conf <<CONF
:box64-i386:M::\x7fELF\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x03\x00:\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\xff\xff\xff\xff\xff\xfe\xff\xff\xff:$BOX64_BIN:F
CONF

systemctl restart systemd-binfmt 2>/dev/null || {
    # no systemd-binfmt: register by hand
    for f in /etc/binfmt.d/box64.conf /etc/binfmt.d/box64-i386.conf; do
        tr -d '\n' < "$f" > /proc/sys/fs/binfmt_misc/register 2>/dev/null
    done
}

[ -e /proc/sys/fs/binfmt_misc/box64 ] || die "x86_64 handler did not register" \
    "Check that binfmt_misc is available:  ls /proc/sys/fs/binfmt_misc/"
grep -q "^flags:.*F" /proc/sys/fs/binfmt_misc/box64 \
    && ok "x86_64 handler registered with the F flag" \
    || { bad "registered, but WITHOUT the F flag"; note "it will not work inside containers"; }
[ -e /proc/sys/fs/binfmt_misc/box64-i386 ] \
    && ok "i386 handler registered (SteamCMD is 32-bit)" \
    || note "warning: no i386 handler — SteamCMD will not run"

# --- stage 4: does an amd64 container run at all? ----------------------------
say "Stage 4 — run a trivial amd64 container"

out=$(docker run --rm --platform linux/amd64 debian:trixie-slim uname -m 2>&1)
if [ "$out" = "x86_64" ]; then
    ok "amd64 containers execute under box64"
else
    die "a plain amd64 container could not run" \
        "output: $out" \
        "If this mentions missing libraries, the handler is not static." \
        "That is the known hard part; Path B (a custom arm64 image) is the fallback."
fi

# --- stage 5: the gate that actually decides ---------------------------------
say "Stage 5 — SteamCMD, the real test"
note "SteamCMD is 32-bit x86 and must work before the server binary even exists."
note "pulling $IMAGE (this takes a while on first run)..."
docker pull -q --platform linux/amd64 "$IMAGE" >/dev/null 2>&1

out=$(docker run --rm --platform linux/amd64 "$IMAGE" \
        bash -c '/opt/steamcmd/steamcmd.sh +quit; echo "STEAMCMD_EXIT=$?"' 2>&1)
echo "$out" | tail -12 | sed 's/^/         /'

if echo "$out" | grep -q "STEAMCMD_EXIT=0" && ! echo "$out" | grep -qi "segmentation fault"; then
    say "RESULT: it works"
    ok "SteamCMD ran under box64. The stock image is usable on this host."
    note ""
    note "Next: point vh.py at this machine and start a server normally."
    note "Re-run this check after any box64 upgrade — this is not a supported"
    note "configuration upstream, so treat it as working-until-proven-otherwise."
    exit 0
else
    say "RESULT: SteamCMD does not run"
    bad "this is the same wall an ARM Mac hits"
    note "The 32-bit half of the emulation is not working. Things to try:"
    note "  - confirm the i386 handler registered (stage 3 above)"
    note "  - confirm box64 was built with -DBOX32=ON"
    note "  - BOX64_LOG=1 docker run --rm --platform linux/amd64 $IMAGE \\"
    note "        /opt/steamcmd/steamcmd.sh +quit"
    note "If it stays broken, the fallback is building an arm64 image (Path B in"
    note "docs/valheim-on-arm.md), which sidesteps binfmt entirely."
    exit 1
fi
