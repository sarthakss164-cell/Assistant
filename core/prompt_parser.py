"""
Multi-Prompt Parser module for LIGHT AI V1.0.
Splits compound spoken utterances into ordered, individual command and question segments.
Supports both punctuated text and plain speech-recognition transcriptions (space-separated).
Preserves original sequence, internal commas and conjunctions in questions,
and handles wake-word prefixes safely.
"""

import re
from typing import List

# Wake-word aliases in Latin and Devanagari
WAKE_WORDS = ("light", "lite", "लाइट")

# Regex to detect leading wake word at the start of an utterance or clause
LEADING_WAKE_REGEX = re.compile(
    r"^\s*(?:light|lite|लाइट)\b\s*[,.:;!-]?\s*",
    re.IGNORECASE
)

# Known applications and websites supported by LIGHT AI
KNOWN_TARGETS = (
    r"chrome|"
    r"google\s+chrome|"
    r"brave|"
    r"brave\s+browser|"
    r"youtube|"
    r"whatsapp(?:\s+web)?|"
    r"notepad|"
    r"notes|"
    r"text\s+editor|"
    r"calculator|"
    r"calc|"
    r"vscode|"
    r"vs\s+code|"
    r"code|"
    r"edge|"
    r"microsoft\s+edge|"
    r"ms\s+edge|"
    r"google|"
    r"browser|"
    r"internet"
)

CANONICAL_TARGET_NAMES = {
    "chrome": "Chrome",
    "google chrome": "Chrome",
    "brave": "Brave",
    "brave browser": "Brave",
    "youtube": "YouTube",
    "whatsapp": "WhatsApp",
    "whatsapp web": "WhatsApp",
    "notepad": "Notepad",
    "notes": "Notepad",
    "text editor": "Notepad",
    "calculator": "Calculator",
    "calc": "Calculator",
    "vscode": "VS Code",
    "vs code": "VS Code",
    "code": "VS Code",
    "edge": "Edge",
    "microsoft edge": "Edge",
    "ms edge": "Edge",
    "google": "Google",
    "browser": "Browser",
    "internet": "Browser",
}

HINDI_ACTION_SUFFIX_OPT = r"(?:\s+(?:open\s+karo|open\s+kar\s+do|khol\s+do|kholo|chalao|karo|please))?"

PAT_PREFIX = re.compile(
    rf"^(?:open|kholo|start|launch)\s+({KNOWN_TARGETS}){HINDI_ACTION_SUFFIX_OPT}$",
    re.IGNORECASE
)
PAT_SUFFIX = re.compile(
    rf"^({KNOWN_TARGETS})(?:\s+ko)?\s+(?:kholo|khol\s+do|open(?:\s+karo)?|chalao)(?:\s+please)?$",
    re.IGNORECASE
)

# 1. Action Command Starters (English and Hindi)
# Matches with or without leading punctuation/conjunctions
ACTION_STARTERS_REGEX = re.compile(
    r"^(?:"
    # App & Website Launchers (strictly matching approved apps and sites)
    rf"(?:open|kholo|launch|start)\s+(?:{KNOWN_TARGETS}){HINDI_ACTION_SUFFIX_OPT}\b|"
    rf"(?:{KNOWN_TARGETS})(?:\s+ko)?\s+(?:kholo|khol\s+do|open(?:\s+karo)?|chalao)(?:\s+please)?\b|"
    # YouTube & Music Commands
    r"(?:play|bajaao|chalaao)\s+[a-zA-Z0-9_\u0900-\u097F]+|"
    r"(?:search|play)\s+.+?\s+on\s+(?:youtube|google)\b|"
    r"youtube\s+(?:search|play|par\s+.+)\b|"
    r"google\s+.+?\b|"
    r"(?:stop|band\s+karo|roko)\s+(?:the\s+)?(?:music|playback|song|songs|gaana|gaane)\b|"
    r"(?:music|song|gaana)\s+(?:band\s+karo|stop\s+karo|roko)\b|"
    # WhatsApp Commands
    r"(?:message|sandesh)\s+[a-zA-Z0-9_]+\b|"
    r"(?:send\s+message\s+to|send\s+whatsapp\s+to|whatsapp)\s+[a-zA-Z0-9_]+\b|"
    # Identity & Assistant Commands
    r"who\s+(?:are|r)\s+(?:you|u)\b|"
    r"hu\s+r\s+u\b|"
    r"who\s+made\s+you\b|"
    r"tum\s+kaun\s+ho\b|"
    r"aap\s+kaun\s+hai\b|"
    r"introduce\s+yourself\b|"
    r"tell\s+me\s+about\s+yourself\b|"
    # Exit / Shutdown Commands
    r"exit\b|"
    r"stop\s+listening\b|"
    r"terminate\b|"
    r"good\s*bye\b|"
    r"bye(?:\s+bye)?\b|"
    r"shut\s*down\b|"
    r"shutdown\b|"
    r"band\s+ho\s+jao\b|"
    r"bas\s+karo\b"
    r")",
    re.IGNORECASE
)

# 2. Complete Standalone Actions
COMPLETE_ACTION_REGEX = re.compile(
    r"^(?:"
    rf"(?:open|kholo|launch|start)\s+(?:{KNOWN_TARGETS}){HINDI_ACTION_SUFFIX_OPT}|"
    rf"(?:{KNOWN_TARGETS})(?:\s+ko)?\s+(?:kholo|khol\s+do|open(?:\s+karo)?|chalao)(?:\s+please)?|"
    r"who\s+(?:are|r)\s+(?:you|u)|"
    r"hu\s+r\s+u|"
    r"who\s+made\s+you|"
    r"tum\s+kaun\s+ho|"
    r"aap\s+kaun\s+hai|"
    r"introduce\s+yourself|"
    r"tell\s+me\s+about\s+yourself|"
    r"exit|stop\s+listening|shutdown|band\s+ho\s+jao|goodbye|bye|"
    r"(?:stop|band\s+karo)\s+(?:music|gaana)"
    r")$",
    re.IGNORECASE
)


# 3. Conversational Question Starters (standalone queries)
QUESTION_STARTERS_REGEX = re.compile(
    r"^(?:"
    r"what\s+(?:is|are|was|were|do|does|did)\b|"
    r"who\s+(?:is|was|were|are)\b|"
    r"where\s+(?:is|are|was|were)\b|"
    r"how\s+(?:to|do|does|did|is|are|can)\b|"
    r"why\s+(?:is|are|do|does|did)\b|"
    r"when\s+(?:did|was|is|will)\b|"
    r"which\s+(?:is|are|was|were|one)\b|"
    r"tell\s+me\s+(?:what|who|where|how|why|when|about)\b|"
    r"can\s+you\s+(?:tell\s+me|explain)\b|"
    r"could\s+you\s+(?:tell\s+me|explain)\b|"
    r"explain\s+.+|"
    r"batao\s+.+|"
    r"kripya\s+batao\s+.+|"
    r"kya\s+hai\b|"
    r"kaun\s+hai\b"
    r")",
    re.IGNORECASE
)

# 3b. Independent Direct Question Starters for candidate right segments
INDEPENDENT_QUESTION_STARTERS_REGEX = re.compile(
    r"^(?:"
    r"what\s+(?:is|are|was|were|do|does|did)\b|"
    r"who\s+(?:is|was|were|are)\b|"
    r"where\s+(?:is|are|was|were|can|do|does|did)\b|"
    r"how\s+(?:can|do|does|did|is|are|to)\b|"
    r"why\s+(?:is|are|do|does|did)\b|"
    r"when\s+(?:did|was|is|will)\b|"
    r"which\s+(?:is|are|was|were|one)\b|"
    r"kya\s+hai\b|"
    r"kaun\s+hai\b|"
    r"kahan\s+hai\b|"
    r"kaise\s+(?:karein|kare|hota\s+hai)\b"
    r")",
    re.IGNORECASE
)

# Combined Boundary Pattern matching delimiters, conjunctions, or word spaces
# that can precede a new segment
BOUNDARY_SPLIT_REGEX = re.compile(
    r"(?:"
    r"[.?!\n;]+\s*|"                                       # Sentence endings
    r",\s*(?:and\s+then|aur\s+phir|and|then|aur|phir)\s+|" # Comma + Conjunction
    r",\s*|"                                               # Comma
    r"\s+(?:and\s+then|aur\s+phir|and|then|aur|phir)\s+|"   # Conjunction only
    r"\s+"                                                 # Plain whitespace (Speech recognition)
    r")",
    re.IGNORECASE
)

# Incomplete clause or dangling connector pattern at the end of candidate_left
INCOMPLETE_LEFT_REGEX = re.compile(
    r"\b(?:"
    r"to|that|of|for|with|in|on|at|from|by|about|between|into|through|"
    r"how|what|why|where|when|who|which|"
    r"me|us|my|our|your|"
    r"tell|explain|know|say|ask|"
    r"ko|ki|ke|ka|par|mein|se|liye|aur|ya|taaki|"
    r"kaise|kyun|kya|kab|kahan|kise|kisko|"
    r"batao|batayein|batana|samjhao|bata|bataiye"
    r")$",
    re.IGNORECASE
)

# Incomplete lead-in request phrases that must not stand alone on candidate_left
INCOMPLETE_LEADIN_REGEX = re.compile(
    r"^\s*(?:"
    r"(?:can|could|would)\s+you(?:\s+please)?(?:\s+(?:tell\s+me|tell|explain|show\s+me|show|say|play|open|search|batao|kholo))?|"
    r"(?:please|kripya|zara)(?:\s+(?:can|could|would)\s+you)?(?:\s+(?:tell\s+me|tell|explain|show\s+me|show|say|play|open|search|batao|kholo))?|"
    r"(?:please\s+)?(?:tell\s+me|tell\s+us|show\s+me|show\s+us|explain|explain\s+to\s+me)|"
    r"(?:do\s+you\s+know)|"
    r"(?:kripya\s+)?(?:mujhe\s+)?(?:batao|batayein|batana|samjhao|bataiye)"
    r")\s*$",
    re.IGNORECASE
)

# Standalone Hindi verb suffixes that belong to preceding noun/song phrase rather than starting a new command
HINDI_VERB_ONLY_REGEX = re.compile(
    r"^(?:play\s+karo|play\s+kar\s+do|chalao|bajaao|sunao)(?:\s+please)?$",
    re.IGNORECASE
)


def strip_leading_wake_word(text: str) -> str:
    """
    Strips leading wake word prefix ('Light', 'lite', 'लाइट') if present at the start of text.
    Preserves any internal occurrences of 'light' (e.g. 'speed of light').
    """
    if not text:
        return ""
    m = LEADING_WAKE_REGEX.match(text)
    if m:
        return text[m.end():].strip()
    return text.strip()


def canonicalize_command_segment(text: str) -> str:
    """
    Normalizes recognized Hindi/Hinglish command segments to standard canonical form.
    E.g.:
      'YouTube open karo' -> 'open YouTube'
      'open YouTube karo' -> 'open YouTube'
      'open YouTube open karo' -> 'open YouTube'
      'Brave kholo' -> 'open Brave'
    """
    clean = text.strip()
    m_pref = PAT_PREFIX.match(clean)
    if m_pref:
        target = " ".join(m_pref.group(1).lower().split())
        canon = CANONICAL_TARGET_NAMES.get(target, target.title())
        return f"open {canon}"
    m_suf = PAT_SUFFIX.match(clean)
    if m_suf:
        target = " ".join(m_suf.group(1).lower().split())
        canon = CANONICAL_TARGET_NAMES.get(target, target.title())
        return f"open {canon}"
    return clean


def split_multi_prompt(raw_text: str) -> List[str]:
    """
    Parses a spoken utterance and splits it into an ordered list of individual prompt segments.
    Supports both plain continuous speech (space-separated) and punctuated text.

    Rules:
    - Strips leading wake word from the head of the utterance.
    - Preserves internal commas, conjunctions, and lists inside questions.
    - Splits when an action command starter follows a word boundary or delimiter.
    - Splits when a question starter follows a completed action command or sentence delimiter.
    - Preserves original chronological sequence.
    - Returns a 1-item list [clean_text] if no valid boundaries exist.
    """
    if not raw_text or not isinstance(raw_text, str):
        return []

    stripped = strip_leading_wake_word(raw_text)
    if not stripped:
        return []

    # Find all potential split boundaries in the text (punctuation, conjunctions, or word spaces)
    delimiters = list(BOUNDARY_SPLIT_REGEX.finditer(stripped))
    if not delimiters:
        return [canonicalize_command_segment(stripped)]

    segments: List[str] = []
    seg_start = 0

    for d in delimiters:
        candidate_left = stripped[seg_start:d.start()].strip()
        candidate_right = stripped[d.end():].strip()

        if not candidate_left:
            seg_start = d.end()
            continue

        # Check if candidate_right has an embedded wake word at its head
        embedded_wake = False
        m_wake = LEADING_WAKE_REGEX.match(candidate_right)
        if m_wake:
            embedded_wake = True
            candidate_right_nowake = candidate_right[m_wake.end():].strip()
        else:
            candidate_right_nowake = candidate_right

        # Must have at least one meaningful word on the right
        if not re.search(r"[a-zA-Z\u0900-\u097F]{2,}", candidate_right_nowake):
            continue

        delim_text = d.group(0).strip()
        is_sentence_ender = any(p in delim_text for p in (".", "?", "!", ";", "\n"))

        # Candidate left sanity checks:
        # A valid left segment must have at least 2 words unless it is an approved standalone exit command
        left_words = candidate_left.split()
        if len(left_words) < 2 and candidate_left.lower() not in (
            "exit", "stop", "terminate", "goodbye", "bye", "shutdown"
        ):
            continue

        # Prevent splitting if candidate_left ends with dangling prepositions, particles, or connectors
        if INCOMPLETE_LEFT_REGEX.search(candidate_left):
            continue

        # Prevent splitting if candidate_left is merely an introductory lead-in phrase
        if INCOMPLETE_LEADIN_REGEX.match(candidate_left):
            continue

        right_is_command = bool(ACTION_STARTERS_REGEX.match(candidate_right_nowake)) and not bool(HINDI_VERB_ONLY_REGEX.match(candidate_right_nowake))
        right_is_question = bool(QUESTION_STARTERS_REGEX.match(candidate_right_nowake))
        right_is_independent_question = bool(INDEPENDENT_QUESTION_STARTERS_REGEX.match(candidate_right_nowake))
        left_is_action = bool(ACTION_STARTERS_REGEX.match(candidate_left))
        left_is_complete_action = bool(COMPLETE_ACTION_REGEX.match(candidate_left))
        left_is_question = bool(QUESTION_STARTERS_REGEX.match(candidate_left)) and len(left_words) >= 3

        # Check if candidate_right starts with a subordinate question continuation
        # (e.g. "how is it measured" / "and how does it work") -> do not split if left is a question
        is_subordinate_question = bool(
            re.match(r"^(?:and\s+)?how\s+(?:is|was|does|did)\s+(?:it|this|that|they)\b", candidate_right_nowake, re.I)
            or re.match(r"^how\s+(?:is|was|does|did)\s+it\b", candidate_right_nowake, re.I)
            or re.match(r"^(?:and\s+)?what\s+(?:is|are)\s+(?:it|this|that|they)\b", candidate_right_nowake, re.I)
        )

        has_punctuation = any(p in delim_text for p in (",", ".", "?", "!", ";", "\n"))
        has_conjunction = bool(re.search(r"\b(?:and|aur|phir|then)\b", delim_text, re.I))

        should_split = False
        if embedded_wake and (right_is_command or right_is_question):
            should_split = True
        elif is_sentence_ender and (right_is_command or right_is_question):
            should_split = True
        elif has_punctuation and left_is_complete_action:
            should_split = True
        elif (has_punctuation or has_conjunction) and (right_is_command or right_is_question) and not is_subordinate_question:
            should_split = True
        elif (left_is_action or left_is_complete_action or left_is_question) and (right_is_command or right_is_question) and not is_subordinate_question:
            should_split = True

        if should_split:
            segments.append(candidate_left)
            seg_start = d.end()

    # Append remaining tail
    remaining_tail = stripped[seg_start:].strip()
    if remaining_tail:
        if remaining_tail.endswith(".") and not remaining_tail.endswith(".."):
            remaining_tail = remaining_tail[:-1].strip()
        if remaining_tail:
            segments.append(remaining_tail.strip())

    # Post-process cleanup
    cleaned_segments = []
    for s in segments:
        s_clean = strip_leading_wake_word(s).strip()
        s_clean = s_clean.rstrip(",;").strip()
        if re.search(r"[a-zA-Z\u0900-\u097F]{2,}", s_clean):
            cleaned_segments.append(canonicalize_command_segment(s_clean))

    return cleaned_segments if cleaned_segments else [canonicalize_command_segment(stripped)]
