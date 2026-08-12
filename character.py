"""Decodes the CharacterData the game sends in the CharacterCallback_T RPC.

This is where the win is: the server sends absolute LEVEL and XP, ready to
use, for both class and job. Nothing is estimated from a progress bar and the
user is never asked to type anything.

The field order is not guessable — it comes from the game's own format, mapped
by spirit-vale-tools (MIT). Reading it out of order does not "fail": it hands
back a wrong number wearing the face of a right one. That is why the reader
stops at the four fields we care about instead of walking the whole structure:
the fewer fields crossed, the fewer chances of drifting off the rails.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from reader import Reader, InvalidPayload, TruncatedPayload

# Character UIDs are GUIDs. The original decoder discards this field, but code
# that searches for the structure blind (see fishnet.hunt) needs every scrap of
# evidence it can get: requiring the format here killed a false positive that
# showed up alongside every genuine reading, with a GUID parsed as the name.
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
                  r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

# The game's own ceilings. These double as a sanity check: a value outside
# them means the read drifted, not that the player is special.
MAX_CLASS_LEVEL = 150
MAX_JOB_LEVEL = 70
MAX_XP = 10_000_000_000


@dataclass(frozen=True)
class Progress:
    """Everything the XP meter needs."""

    name: str
    level: int
    xp: int
    job_level: int
    job_xp: int

    def plausible(self) -> bool:
        return (1 <= self.level <= MAX_CLASS_LEVEL
                and 1 <= self.job_level <= MAX_JOB_LEVEL
                and 0 <= self.xp <= MAX_XP
                and 0 <= self.job_xp <= MAX_XP)


def decode(payload: bytes, with_update_type: bool,
           require_guid: bool = False) -> Progress | None:
    """Reads the head of a CharacterData up to the progress fields.

    `with_update_type` is True for CharacterCallback_T, which prefixes the
    structure with one extra enum.

    `require_guid` demands that the UID look like a GUID. Off by default so
    this stays faithful to the original decoder, which merely discards that
    field; blind searches turn it on.

    Returns None when the payload does not match the format — deliberately.
    Admitting we did not understand beats handing back an invented number.
    """
    try:
        reader = Reader(payload)
        if with_update_type:
            reader.packed()              # CharacterUpdateType

        reader.object_marker()
        uid = reader.text(80)
        if require_guid and not (uid and GUID.match(uid)):
            return None
        reader.text(80)                  # account id, discarded
        reader.packed()
        reader.text(80)
        reader.text(80)
        name = reader.text(64) or "?"

        reader.object_marker()
        for _ in range(10):
            reader.packed()
        reader.object_marker()
        reader.booleans()
        # titles/achievements: each entry has its own shape
        reader.list_of(lambda: (reader.object_marker(), reader.packed(),
                                reader.text(256), reader.packed(),
                                reader.boolean()))
        reader.text(256)                 # title
        reader.text(256)
        reader.text(256)
        reader.list_of(reader.packed)    # archetypes

        # finally, what we came for
        level = reader.packed()
        xp = reader.packed()
        job_level = reader.packed()
        job_xp = reader.packed()
    except (TruncatedPayload, InvalidPayload):
        return None

    progress = Progress(name=name, level=level, xp=xp,
                        job_level=job_level, job_xp=job_xp)
    return progress if progress.plausible() else None
