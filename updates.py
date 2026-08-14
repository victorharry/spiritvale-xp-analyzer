"""Asks GitHub whether a newer release exists.

The app ships as an .exe people download once and forget about. Without this,
a fix only reaches whoever happens to revisit the page — everyone else keeps
running the old build and reporting bugs that no longer exist.

One HTTP request to the public Releases API, at startup, in a background
thread. No account, no token, no telemetry: the request carries nothing but a
User-Agent, and nothing is sent back. If GitHub is unreachable, rate-limited or
slow, the check simply does not happen — an update notice is never worth
delaying or breaking the program over, so every failure here is silent.

The version below is the single source of truth. `verify_build.py` refuses to
package a build whose installer.iss disagrees with it.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from typing import Callable, NamedTuple

VERSION = "2.2.0"

REPO = "victorharry/spiritvale-xp-analyzer"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"

# short on purpose: this runs while the user is opening the program, and a
# stalled connection must not hold the overlay back
TIMEOUT = 6.0


class Release(NamedTuple):
    version: str          # without the leading "v": "2.1.0"
    url: str              # the page to open when the banner is clicked


def _numbers(tag: str) -> tuple[int, ...]:
    """The comparable part of a tag: "v2.1.0-beta" -> (2, 1, 0).

    Tags are typed by hand at release time, so this reads them loosely: with
    or without the "v", with or without a pre-release suffix.
    """
    core = re.split(r"[-+]", tag.strip().lstrip("vV"), maxsplit=1)[0]
    return tuple(int(part) for part in re.findall(r"\d+", core))


def is_newer(candidate: str, current: str = VERSION) -> bool:
    """Whether `candidate` is a later version than `current`.

    Compares field by field, padding the shorter one with zeros, so "2.1"
    and "2.1.0" are the same version rather than different ones.
    """
    a, b = _numbers(candidate), _numbers(current)
    if not a:
        return False                      # a tag with no digits says nothing
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def latest() -> Release | None:
    """The newest published release, or None if it could not be found out.

    None is not an error to report. It means "no answer": offline, blocked by
    a firewall, GitHub throttling this address. The caller shows nothing.
    """
    request = urllib.request.Request(
        LATEST_API,
        headers={"Accept": "application/vnd.github+json",
                 # GitHub rejects requests with no User-Agent
                 "User-Agent": f"XP-Analyzer/{VERSION}"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
            data = json.loads(answer.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None
    if not isinstance(data, dict) or data.get("draft"):
        return None
    tag = str(data.get("tag_name") or "").strip()
    if not tag:
        return None
    return Release(tag.lstrip("vV"), str(data.get("html_url") or RELEASES_PAGE))


def check_in_background(on_update: Callable[[Release], None],
                        skipped: str = "") -> None:
    """Looks for a newer release and calls `on_update` only if there is one.

    `skipped` is a version the user already dismissed; it never comes back.
    Being told once is a service, being told every launch is nagging.

    The callback runs on this thread, not the interface one — whoever passes it
    is responsible for handing the result over to the UI thread (the app does
    it through its queue).
    """
    def run() -> None:
        release = latest()
        if release and is_newer(release.version) and release.version != skipped:
            try:
                on_update(release)
            except Exception:
                pass                      # a broken notice must not raise here
    threading.Thread(target=run, daemon=True, name="update-check").start()
