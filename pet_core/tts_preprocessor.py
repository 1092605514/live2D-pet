"""
Clean and segment LLM text for natural TTS output.

LLM replies often contain markdown, emojis, JSON fragments, and formatting
that sounds robotic or garbled when read aloud. This module strips those
artifacts and segments text into natural speech chunks.
"""

import re
from typing import Optional

# ── Markdown stripping ──────────────────────────────────────

# Images: ![alt](url) → remove entirely
_RE_MD_IMAGE = re.compile(r"!\[.*?\]\(.*?\)")
# Links: [text](url) → "text"
_RE_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
# Bold/italic: **text**, *text*, __text__, _text_ → "text"
_RE_MD_BOLD_ITALIC = re.compile(r"(\*{1,3}|_{1,3})(.+?)\1")
# Inline code: `code` → remove
_RE_MD_INLINE_CODE = re.compile(r"`[^`]+`")
# Fenced code blocks: ```lang\n...\n``` → remove
_RE_MD_FENCED_BLOCK = re.compile(r"```[\s\S]*?```", re.DOTALL)
# Headings: ## text → "text"
_RE_MD_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
# Horizontal rules: ---, ***, ___
_RE_MD_HRULE = re.compile(r"^[-*_]{3,}\s*$", re.MULTILINE)
# Blockquotes: > text → "text"
_RE_MD_BLOCKQUOTE = re.compile(r"^>\s?", re.MULTILINE)
# Strikethrough: ~~text~~ → "text"
_RE_MD_STRIKE = re.compile(r"~~(.+?)~~")
# HTML tags: <br>, <b>, etc.
_RE_HTML_TAG = re.compile(r"<[^>]+>")

# ── Emoji removal ───────────────────────────────────────────

# Targeted emoji ranges — excludes CJK and other non-emoji supplementary chars
_RE_EMOJI = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols extended-A
    "\U00002702-\U000027B0"  # dingbats
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0000200D"             # zero width joiner
    "\U00002600-\U000026FF"  # misc symbols
    "\U00002700-\U000027BF"  # dingbats
    "\U0000231A-\U0000231B"  # watch, hourglass
    "\U000023E9-\U000023F3"  # media controls
    "\U000023F8-\U000023FA"  # media controls
    "\U000025AA-\U000025AB"  # squares
    "\U000025B6"             # play button
    "\U000025C0"             # reverse button
    "\U000025FB-\U000025FE"  # squares
    "\U00002614-\U00002615"  # umbrella, coffee
    "\U00002648-\U00002653"  # zodiac
    "\U0000267F"             # wheelchair
    "\U00002693"             # anchor
    "\U000026A1"             # lightning
    "\U000026AA-\U000026AB"  # circles
    "\U000026BD-\U000026BE"  # soccer, baseball
    "\U000026C4-\U000026C5"  # snowman, sun
    "\U000026CE"             # ophiuchus
    "\U000026D4"             # no entry
    "\U000026EA"             # church
    "\U000026F2-\U000026F3"  # fountain, golf
    "\U000026F5"             # sailboat
    "\U000026FA"             # tent
    "\U000026FD"             # fuel pump
    "\U00002702"             # scissors
    "\U00002705"             # check mark
    "\U00002708-\U0000270D"  # plane, envelope, etc.
    "\U0000270F"             # pencil
    "\U00002712"             # black nib
    "\U00002714"             # check mark
    "\U00002716"             # multiplication
    "\U0000271D"             # latin cross
    "\U00002721"             # star of david
    "\U00002728"             # sparkles
    "\U00002733-\U00002734"  # eight spoked asterisk
    "\U00002744"             # snowflake
    "\U00002747"             # sparkle
    "\U0000274C"             # cross mark
    "\U0000274E"             # cross mark
    "\U00002753-\U00002755"  # question marks
    "\U00002757"             # exclamation
    "\U00002763-\U00002764"  # heart exclamation
    "\U00002795-\U00002797"  # plus, minus, divide
    "\U000027A1"             # arrow
    "\U000027B0"             # curly loop
    "\U00002934-\U00002935"  # arrows
    "\U00002B05-\U00002B07"  # arrows
    "\U00002B1B-\U00002B1C"  # squares
    "\U00002B50"             # star
    "\U00002B55"             # circle
    "\U00003030"             # wavy dash
    "\U0000303D"             # part alternation mark
    "\U00003297"             # circled ideograph congratulation
    "\U00003299"             # circled ideograph secret
    "]+",
    flags=re.UNICODE,
)

# ── JSON fragment removal ───────────────────────────────────

# Catch JSON command fragments that leaked through strip_command_block
_RE_JSON_KV = re.compile(
    r'[\s,]*"(?:action|expression|text)"\s*:\s*"[^"]*"',
    re.DOTALL,
)
_RE_JSON_OBJ = re.compile(
    r'\{[^{}]*"(?:action|expression|text)"\s*:[^{}]*\}',
    re.DOTALL,
)
_RE_FENCE_REMNANT = re.compile(r"```(?:json|JSON)?\s*$|^\s*```", re.MULTILINE)

# ── URL and mention removal ─────────────────────────────────

_RE_URL = re.compile(r"https?://\S+")
_RE_MENTION = re.compile(r"@\w+")

# ── Punctuation normalization ───────────────────────────────

# Chinese-style repetition: ！！！→ ！，？？？→ ？
_RE_PUNCT_REPEAT = re.compile(r"([。！？~!?])\1{2,}")
# Mixed Chinese/English punctuation cleanup
_RE_SPACE_BEFORE_PUNCT = re.compile(r"\s+([。！？，、；：~])")
_RE_PUNCT_AFTER_SPACE = re.compile(r"([。！？，、；：~])\s{2,}")


def clean_for_tts(text: str) -> str:
    """Clean LLM text for natural TTS synthesis.

    Strips markdown, emojis, JSON fragments, URLs, and normalizes punctuation.
    Returns text that sounds natural when read aloud.
    """
    if not isinstance(text, str):
        return ""

    # 1. Remove JSON objects/fragments first (before markdown, as ``` fences confuse it)
    text = _RE_JSON_OBJ.sub("", text)
    text = _RE_JSON_KV.sub("", text)

    # 2. Strip markdown (fenced blocks before fence remnants)
    text = _RE_MD_IMAGE.sub("", text)
    text = _RE_MD_LINK.sub(r"\1", text)
    text = _RE_MD_FENCED_BLOCK.sub("", text)
    text = _RE_FENCE_REMNANT.sub("", text)
    text = _RE_MD_INLINE_CODE.sub("", text)
    text = _RE_MD_STRIKE.sub(r"\1", text)
    text = _RE_MD_HRULE.sub("", text)
    text = _RE_MD_HEADING.sub("", text)
    text = _RE_MD_BLOCKQUOTE.sub("", text)
    text = _RE_MD_BOLD_ITALIC.sub(r"\2", text)
    text = _RE_HTML_TAG.sub("", text)

    # 3. Remove emojis
    text = _RE_EMOJI.sub("", text)

    # 4. Remove URLs and mentions
    text = _RE_URL.sub("", text)
    text = _RE_MENTION.sub("", text)

    # 5. Normalize punctuation
    # Collapse repeated punctuation: ！！！→ ！
    text = _RE_PUNCT_REPEAT.sub(r"\1", text)
    # Remove spaces before Chinese punctuation
    text = _RE_SPACE_BEFORE_PUNCT.sub(r"\1", text)
    # Collapse multiple spaces after punctuation to single
    text = _RE_PUNCT_AFTER_SPACE.sub(r"\1 ", text)

    # 6. Normalize whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    return text


def segment_sentences(text: str, max_chars: int = 100) -> list[str]:
    """Split text into natural speech segments for TTS.

    Segments at sentence boundaries (。！？~.!?) and clause boundaries (，、；：).
    Each segment is at most `max_chars` characters. Short segments are merged
    with their neighbors to avoid choppy speech.

    Returns a list of strings, each suitable for a single TTS call.
    """
    if not isinstance(text, str) or not text.strip():
        return []

    text = text.strip()

    # If short enough, return as single segment
    if len(text) <= max_chars:
        return [text]

    # Primary split: sentence-ending punctuation
    sentence_pattern = re.compile(r"(?<=[。！？~!?])\s*")
    raw_segments = sentence_pattern.split(text)

    # Merge short segments and split long ones at clause boundaries
    result: list[str] = []
    buffer = ""

    for seg in raw_segments:
        seg = seg.strip()
        if not seg:
            continue

        if len(buffer) + len(seg) + 1 <= max_chars:
            buffer = f"{buffer}{seg}" if buffer else seg
        else:
            if buffer:
                result.append(buffer)
            # If segment itself is too long, split at clause boundaries
            if len(seg) > max_chars:
                clauses = _split_at_clauses(seg, max_chars)
                result.extend(clauses[:-1])
                buffer = clauses[-1] if clauses else ""
            else:
                buffer = seg

    if buffer:
        result.append(buffer)

    return result


def _split_at_clauses(text: str, max_chars: int) -> list[str]:
    """Split long text at clause boundaries (，、；：)."""
    clause_pattern = re.compile(r"(?<=[，、；：,;:])\s*")
    parts = clause_pattern.split(text)

    result: list[str] = []
    buffer = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(buffer) + len(part) + 1 <= max_chars:
            buffer = f"{buffer}{part}" if buffer else part
        else:
            if buffer:
                result.append(buffer)
            # If still too long, force-split at max_chars
            while len(part) > max_chars:
                result.append(part[:max_chars])
                part = part[max_chars:]
            buffer = part

    if buffer:
        result.append(buffer)

    return result if result else [text]


def prepare_tts_text(
    text: str,
    *,
    max_segment_chars: int = 100,
    add_ending: bool = True,
    ending_char: str = "~",
) -> list[str]:
    """Full TTS text pipeline: clean → segment → add natural endings.

    Returns a list of speech segments ready for TTS synthesis.
    """
    cleaned = clean_for_tts(text)
    if not cleaned:
        return []

    segments = segment_sentences(cleaned, max_chars=max_segment_chars)

    if add_ending and segments:
        last = segments[-1]
        if last and not last.endswith(("~", "！", "？", "。", "!", "?", ".")):
            segments[-1] = last + ending_char

    return segments
