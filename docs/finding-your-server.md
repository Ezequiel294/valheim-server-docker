# Finding your server

The server starting is only half the job — Valheim gives you several ways to
connect and they behave differently. When the log says something like

```
Game server connected
```

it is up. Here is how people actually get in.

## The two ports

| Port | What it is |
| --- | --- |
| `2456/udp` | the **game** port — where players connect (`SERVER_PORT`) |
| `2457/udp` | the **query** port — always `SERVER_PORT + 1`; Steam's browser and the status page ask this one |
| `2458/udp` | only with `CROSSPLAY: "true"` (and for mods that use RPC) |

The `+ 1` catches everybody out: the port you type into Steam's "add server" box
is **not** the port you set in the config.

If you change `SERVER_PORT`, change the `ports:` mapping in your instance file to
match — the query port moves with it.

## Joining directly by IP — the reliable one

In-game: **Join Game → Join IP**, then type the address.

- On the default port, the hostname or IP alone is enough: `example.com`
- On any other port, include it: `example.com:3333`

**This works even when `SERVER_PUBLIC` is `false`.** If you only play with people
you can send an address to, an unlisted server plus this method is the simplest
setup there is — and it is what `vh.py create` tells you when you choose not to
list the server.

For players outside your network you need UDP 2456–2457 forwarded to the machine
running Docker, and allowed through its firewall. With crossplay on, that is not
required — PlayFab relays the connection.

## The in-game Community browser

**Join Game → Community**. The list holds thousands of servers and shows 200 at a
time, so type part of your server name into the filter rather than scrolling.

Requires `SERVER_PUBLIC: "true"` (the default).

## Steam's server browser

In Steam: **View → Servers**, **Change Filters**, pick game *Valheim*, let the
list load, then sort by the server column and find yours. Right-click to
favourite it.

Requires `SERVER_PUBLIC: "true"`. Expect to enter the password twice — once in
Steam and once in-game.

Upstream keeps a screenshot walkthrough of this, and of the Community browser,
in [the container's README](https://github.com/community-valheim-tools/valheim-server-docker#finding-your-server).

## Steam favourites and LAN play

This is the route for playing on your own network, and it is the one with the
footguns.

1. Steam → **View → Servers**
2. **Favorites** tab → **Add Server**
3. Enter the IP and **port + 1** — for the default port that is `192.168.1.10:2457`
4. **Find games at this address...**
5. **Add selected game server to favorites...**

Do *not* use *Add this address to favorites* at step 5 — it adds an entry that
does not resolve.

Two things that break this:

- **`SERVER_PUBLIC: "false"`.** A private server does not answer Steam queries,
  so the address returns *Server is not responding*. Use Join IP instead.
- **`CROSSPLAY: "true"`.** Crossplay moves matchmaking from Steam to PlayFab, and
  LAN discovery through the Steam browser stops working. It is Steam-only.

If the server is found but connecting fails, adding it again on the plain game
port (`2456`) with *Add this address to favorites* sometimes fixes the existing
entry rather than creating a second one. Refreshing and immediately
double-clicking also helps. Upstream describes this as hit and miss, and it is.

## Checking from the host

```bash
python vh.py status my-server
```

reports whether the server process is running. For live detail — player count,
version, server name — it reads the container's `status.json`, which needs
**both** `STATUS_HTTP: "true"` **and** `SERVER_PUBLIC: "true"`, because the data
comes from the Steam query port and private servers do not answer it. If those
are not set, `status` says so and names them rather than reporting an error.

## Becoming an admin

Admin commands are in-game, not on the host. Put your SteamID64 in
`ADMINLIST_IDS` (the wizard's access-control topic asks for it), restart, and
press **F5** in-game for the console. Recent Valheim versions need the client
launched with `-console` for F5 to open at all — set that in Steam's launch
options for Valheim.

Your SteamID64 is the 17-digit number shown in-game with **F2**, and in the
server log when you connect.
