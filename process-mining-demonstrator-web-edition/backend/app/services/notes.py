"""Note-writing rules shared by the web API and the MCP server.

Both surfaces append comments to notes, so the comment-header format, the header
de-fanging and the thread capacity check live here and apply to both. The MCP server also
runs every field through ``clean_text`` (limits, control/bidi stripping); the web API
enforces its own limits on its request models.
"""

from __future__ import annotations

import re
import unicodedata

from ..timeutil import local_now

TITLE_MAX = 200     # the web API's NoteUpdateBody.title cap
TEXT_MAX = 4000     # the web API's NoteUpdateBody.comment cap (per comment / new note)
STEP_MAX = 2000     # a step name reference (STEPS.STEP is VARCHAR(2000))
THREAD_MAX = 100_000  # NOTES.NOTE is VARCHAR(100000): the whole thread must fit

# C0/C1 control characters except TAB and LF, plus the Unicode bidi overrides and
# zero-width joiners used to disguise text ("Trojan Source"). CR is folded into LF.
_CONTROL = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u061c\u200b-\u200f\u2028\u2029"
    "\u202a-\u202e\u2066-\u2069\ufeff]"
)


def clean_text(value: object, *, max_len: int, single_line: bool = False) -> str:
    """Normalise user/agent-supplied note text: NFC, CRLF→LF, control and bidi
    characters removed, trimmed. Raises ValueError when it is longer than ``max_len``
    (checked after cleaning, so padding with stripped characters cannot hide length)."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("must be a string")
    text = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    if single_line:
        text = " ".join(text.split())
    text = text.strip()
    if len(text) > max_len:
        raise ValueError(f"is too long ({len(text)} characters; the limit is {max_len})")
    return text


# A thread entry's header is a line starting with "——". Text that a caller supplies must
# never be able to produce such a line (or a title that reads as "· someone else ·"), or a
# commenter could forge an entry that appears to come from another person.
_HEADER_LINE = re.compile(r"^(\s*)——", re.M)


def defang_headers(text: str) -> str:
    """Neutralise any line that would look like a thread-entry header."""
    return _HEADER_LINE.sub(lambda m: m.group(1) + "--", text)


def _safe_title(title: str) -> str:
    return title.replace("——", "--").replace("·", "-")


def comment_block(author_name: str, comment: str, title: str | None = None) -> str:
    """The header + body prepended to a note's thread for one comment (newest on top).
    The stamp is local wall-clock time in the Admin Console display zone. The body and
    title are de-fanged so they cannot imitate another entry's header."""
    stamp = local_now().strftime("%Y-%m-%d %H:%M")
    title = _safe_title(title) if title else None
    header = (
        f"—— {title} · {author_name} · {stamp} ——" if title else f"—— {author_name} · {stamp} ——"
    )
    return f"{header}\n{defang_headers(comment)}\n\n"


def thread_has_room(existing_text: str | None, block: str) -> bool:
    """Whether prepending ``block`` keeps the whole thread within the NOTE column."""
    return len(existing_text or "") + len(block) <= THREAD_MAX
