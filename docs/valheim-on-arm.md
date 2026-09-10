# Running the server on ARM (Raspberry Pi 5)

Valheim's dedicated server is an **x86_64 Linux binary**. Iron Gate publishes no
ARM build, so the container image exists for `linux/amd64` only. Everything below
is about bridging that gap on ARM Linux.

> **Nothing on this page has been tested by the author.** It was assembled from
> box64's documentation, its issue tracker, and reports from people running
> Valheim on Raspberry Pi hardware. The development machine for this repository
> is an ARM Mac, where the whole approach fails for unrelated reasons (see
> below), so the Pi steps are unverified. Treat the ordering as advice about
> which experiment to run first, not as a tested recipe.

## Two ARM cases that are not alike

**ARM macOS — don't.** Docker Desktop emulates an entire x86 system inside a
Linux VM. SteamCMD's core is a *32-bit* x86 binary and it segfaults loading the
Steam API under both Rosetta and the QEMU fallback. Confirmed on Apple Silicon:
the container starts, reports healthy, and retries a download that never lands.

**ARM Linux — workable.** [box64](https://github.com/ptitSeb/box64) is a
userspace translator: it converts x86_64 instructions to ARM64 as the program
runs, natively on Linux, with no virtual machine involved. It is actively
maintained and Valheim-on-a-Pi is one of its known use cases. Reports put a Pi 5
at 30–40% CPU with two players; a Pi 4 has held five players with extra swap.

## Prerequisites on a Raspberry Pi 5

**1. Switch to a 4K-page kernel — not optional.** The Pi 5 defaults to a 16K page
size, and box64/box86 require 4K.

```bash
echo 'kernel=kernel8.img' | sudo tee -a /boot/firmware/config.txt
sudo reboot
getconf PAGESIZE          # must print 4096
```

Costs roughly 5% general system performance. Skipping it is the single most
common reason box64 setups fail on a Pi 5.

**2. 8 GB RAM or more.** Valheim idles near 2.8 GB before anyone joins.

**3. A USB SSD.** Startup and world saves are where the stalls show up, and a
microSD card makes them worse.

## Path A — try the stock image first

Cheapest experiment, and if it works there is nothing to maintain: you get the
upstream image with its Valheim 1.0 chunked-save handling intact, and this repo
works unchanged apart from the `platform:` line `vh.py` already writes.

`scripts/try-box64-binfmt.sh` does the whole sequence for you, on the Pi:

```bash
sudo ./scripts/try-box64-binfmt.sh          # run it
sudo ./scripts/try-box64-binfmt.sh --undo   # put everything back
```

It works in stages and stops at the first failure, so the output names the gate
that broke. The manual steps are below if you would rather do it by hand.

The idea is to register box64 as the kernel's handler for x86_64 executables, so
an `amd64` container's binaries run under box64 instead of QEMU. The `F` flag
matters: it pins the interpreter in memory so it still resolves inside a
container's mount namespace.

```bash
# x86_64 -> box64
sudo tee /etc/binfmt.d/box64.conf >/dev/null <<'CONF'
:box64:M::\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x3e\x00:\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\xff\xff\xff\xff\xff\xfe\xff\xff\xff:/usr/local/bin/box64:F
CONF

# i386 -> box86, because SteamCMD is 32-bit and the server download goes through it
sudo tee /etc/binfmt.d/box86.conf >/dev/null <<'CONF'
:box86:M::\x7fELF\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x03\x00:\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\xff\xff\xff\xff\xff\xfe\xff\xff\xff:/usr/local/bin/box86:F
CONF

sudo systemctl restart systemd-binfmt
cat /proc/sys/fs/binfmt_misc/box64      # flags should include F
```

You do not actually need box86. Building box64 with `-DBOX32=ON` lets it run
32-bit x86 itself, which covers SteamCMD and avoids adding armhf multiarch to a
64-bit Pi OS. Register box64 as the handler for *both* formats — that is what the
i386 entry above does. For a Pi 5 the full configure line is:

```
cmake .. -DRPI5ARM64=1 -DBOX32=ON -DBOX32_BINFMT=ON -DSTATICBUILD=ON \
         -DCMAKE_BUILD_TYPE=RelWithDebInfo
```

`STATICBUILD` is the part that matters most for containers, and it is the part
box64 marks experimental. box64 is an arm64 binary; inside an amd64 container its
arm64 shared libraries do not exist, so a dynamically-linked handler cannot load
— the same failure that bites dynamically-linked qemu. The static build carries
only minimal wrapped libs (libc, libm, libpthread) and takes everything else from
the container's own x86_64 libraries, which for this image is exactly right.

Then the smoke test that actually decides it. **SteamCMD is the gate**, not the
server — the server binary does not exist until SteamCMD fetches it:

```bash
docker run --rm --platform linux/amd64 \
  ghcr.io/community-valheim-tools/valheim-server:latest \
  bash -c '/opt/steamcmd/steamcmd.sh +quit; echo "exit=$?"'
```

`exit=0` and no segfault means Path A is live — point `vh.py` at the Pi and go.
A segfault at `Loading Steam API...` means the 32-bit half is not working, and
that is the same wall the ARM Mac hits.

Be aware this is not a well-supported configuration. box64's static build is
marked experimental and its binfmt `F`-flag request was closed stale rather than
implemented, so treat a working result as a happy discovery rather than a
supported platform, and re-test it after box64 upgrades.

## Path B — build an arm64 image

If Path A fails, the fallback is an arm64 image carrying box64 and box86
internally, built from the upstream project's sources so the Valheim 1.0 backup
logic and the whole documented variable surface survive.

The upstream `Dockerfile` is more amenable to this than it looks. It already
harvests foreign-architecture libraries in a separate stage —

```dockerfile
FROM --platform=linux/386 debian:buster-slim AS i386-libs
```

— which is exactly the technique needed, and that stage carries over unchanged
because SteamCMD stays 32-bit x86 regardless of host. What changes:

- an arm64 base image, plus box64 and box86 installed in it;
- a second foreign-arch stage (`--platform=linux/amd64`) to harvest the *x86_64*
  copies of `libsdl2`, `libcurl4`, `libc6`, `libstdc++6`, `libatomic1` and
  `libpulse` — box64 needs x86_64 shared objects to satisfy the server binary,
  not arm64 ones;
- the Go toolchain download, which hardcodes `linux-amd64`;
- shims so the container's own scripts reach the binaries through box64/box86.

This is a real project with ongoing maintenance attached, not an afternoon's
work, and it means tracking upstream by hand from then on.

## Path C — no Docker

Install box64/box86 and the server directly on Pi OS. The least emulation
overhead and the best-documented route, and it throws away everything the
container gives you: auto-update, scheduled backups, hooks, log filtering. `vh.py`
would have to generate systemd units instead of compose files.

## Path D — an x86_64 host

An old PC, a NAS, or a small VPS runs this repo exactly as built, with no
emulation, no page-size surgery and no caveats. Worth pricing before committing
to weeks of Path B.

## If it runs but misbehaves

- **Crashes 5–20 minutes in, nothing in the log.** Reported by several Pi users.
  Usually memory pressure or a box64 dynarec issue; try more swap first, then
  `BOX64_DYNAREC=0` to confirm the cause — but note that disabling dynarec makes
  the server *drastically* slower, to the point of taking many minutes to open a
  socket. It is a diagnostic, not a configuration.
- **A Valheim update breaks it.** The game auto-updates through SteamCMD
  independently of the image, so a new build can land on box64 before box64 has
  been tested against it. Pin `UPDATE_CRON` off and update deliberately if this
  bites, and keep backups you have actually restored from once.
- **Backups.** Whatever path you take, verify a restore before trusting it. A
  Valheim 1.0 world is a directory of chunk files and a mid-save copy can be
  inconsistent — see [valheim-1.0-worlds.md](valheim-1.0-worlds.md).
