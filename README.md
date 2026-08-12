# XP Analyzer

A small overlay for **SpiritVale** that shows how long until your next class
and job level — with XP per hour and a live rate chart — in a window you drag
over the game.

Nothing to type in, nothing to calibrate. Your level and XP come straight from
the game server, and the cost of every level comes from the game's own table.

### 📥 [Download](https://github.com/victorharry/spiritvale-xp-analyzer/releases/latest) &nbsp;·&nbsp; 📊 [How levelling actually works](https://victorharry.github.io/spiritvale-xp-analyzer/)

The second link is worth a look on its own: it explains the XP curve, why no
formula reproduces it, and lists the full table for all 150 levels.

---

## It needs to run as administrator

Windows will ask for permission every time you open it. Click Yes.

That is not a bug and it is not optional. The XP Analyzer reads the network
packets the game server already sends to your computer — that is where the
exact level and XP come from. On Windows, reading the network is a privileged
operation, **even when a program only ever looks and never sends anything**.

**If you would rather not see the prompt**, install
[Npcap](https://npcap.com/#download) — a network reader that holds the
permission for you. Untick *"Restrict Npcap driver's access to Administrators
only"* during its install. The XP Analyzer picks it up automatically and stops
needing elevation. It is the same component the Spirit Vale Overlay uses, so
if you already run that one, you already have it.

## What it does and does not do

**Does:** reads network packets that are already arriving on this machine.

**Does not:**

- never reads or writes the game's memory — there is not one line of code in
  this repository capable of it
- never sends, injects or modifies a packet
- never automates anything in the game: no clicking, no mouse, no keys

The capture is passive and non-promiscuous: this machine's traffic only, read
only.

## Running from source

```bash
pip install -r requirements.txt
python xp_analyzer.py
```

The only third-party dependency is `customtkinter`. Everything else — network
capture, packet decoding, the UI — is the Python standard library.

To build the `.exe` and the installer, run `Build.bat` and then `Installer.bat`.

---

## Where things live

### Reading the network → `pcap.py`, `rawsocket.py`, `ports.py`

Two ways to capture, with opposite trade-offs, and the app uses whichever is
available. `pcap.py` talks to Npcap through ctypes — no pip package, just the
system DLL. `rawsocket.py` is the fallback that needs no install but does need
administrator. `ports.py` asks Windows which UDP ports belong to the game
process, so the decoder only ever sees the game's traffic.

### Decoding the packets → `ip.py`, `litenetlib.py`, `fishnet.py`, `reader.py`, `character.py`

Four formats are stacked, and all four have to be unwrapped:

```
UDP → LiteNetLib → FishNet → CharacterData
```

`ip.py` strips IP and UDP. `litenetlib.py` handles merged datagrams and
reassembles fragments. `fishnet.py` reassembles split messages and finds the
character inside them. `reader.py` implements FishNet's wire format
(zigzag varints, length-prefixed strings). `character.py` decodes the fields we
want: name, level, XP, job level, job XP.

The packet layer is a Python port of the format mapped by
[spirit-vale-tools](https://github.com/kar-mi/spirit-vale-tools) (MIT).

### Putting it together → `capture.py`

One thread: opens a capture, filters to the game's ports, walks the layers
above and publishes the latest reading. The rest of the app just asks it what
the newest progress is.

### The level table → `xp_table.py`, `extract_table.py`

`xp_table.py` is how much XP each of the 161 levels costs — the game's own
table, extracted from the client, not an estimate. `extract_table.py`
regenerates it after a patch: it searches by the table's *shape* rather than a
fixed address, then checks the result against independent measurements.

Why the table is in the client at all, and why no formula reproduces it, is
[the story on the site](https://victorharry.github.io/spiritvale-xp-analyzer/).

### Update check → `updates.py`

One request to GitHub's public Releases API at startup, in a background thread.
If a newer version is out, a small banner appears at the top of the overlay
with a link; closing it means that version is never mentioned again. Nothing is
sent, nothing is downloaded, and if GitHub is unreachable the check silently
does not happen. `updates.VERSION` is the single source of truth for the
version number — `verify_build.py` refuses to package a build whose
`installer.iss` disagrees with it.

To turn it off, set `"update_check": false` in `config.json` (next to the .exe
when running from source, in `%APPDATA%\XP Analyzer` when installed).

### The interface → `xp_analyzer.py`, `window.py`, `xp.py`, `settings.py`

`xp_analyzer.py` is the entry point and the glue. `window.py` is the overlay
itself — three screens (waiting, full, compact) plus the rate chart. `xp.py`
computes the rate over a rolling window and the time-to-level. `settings.py`
holds config, DPI and console setup.

### Tools → `listen.py`, `verify_build.py`, `find_formula.py`

`listen.py` prints readings live in a console — the first thing to run when
nothing shows up. `verify_build.py` checks a packaged build is whole before it
becomes an installer. `find_formula.py` is the search that tried, and failed,
to find a formula behind the XP curve; it stays as the evidence for why the
table is a table.

### `tests/`

Seven suites, no framework — plain scripts that print what they checked and exit
non-zero on failure. `test_network.py` builds a real packet from the inside out
(fragmented, out of order, merged, VLAN-tagged) and asserts the whole stack
unwraps it. `test_xp_table.py` checks the extracted table against measurements
taken a completely different way.

```bash
python tests/test_network.py
```

---

## Credits

The packet format was mapped by
[spirit-vale-tools](https://github.com/kar-mi/spirit-vale-tools) (MIT). This
project is an independent Python implementation that reuses that knowledge.

Not affiliated with, endorsed by, or connected to the developers of SpiritVale.
