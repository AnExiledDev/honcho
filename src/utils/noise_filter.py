"""Operational-noise classification for deriver ingestion.

Some uploaded messages carry no derivable substance: agent-harness
breadcrumbs (``[Tool]``/``[Git External]`` lines), bare tool-use / task IDs,
empty bodies, and control handshakes ("say BEGIN and then stop"). Deriving
conclusions from them produces junk representation facts *and* spends model
tokens, so the deriver skips the representation task for them (see
``src.deriver.enqueue.generate_queue_records``).

Design intent — **conservative**. A false positive here silently drops real
content from a peer's representation, which is worse than missing a breadcrumb.
So this classifier only fires when the *entire* message is operational noise:

* it does NOT fire because a substantive message merely *contains* a ``/tmp``
  path, a percentage/stat, or an ID mid-sentence — that softer "ignore noise
  within a message" guidance is carried by the deriver ``custom_instructions``,
  not by this hard skip;
* the leading-tag set is limited to known harness tags, each of which must be a
  complete bracketed tag (optionally with a ``:`` suffix), so prose like
  ``[Note] ...`` or ``[Tool tips for cooking]`` is left alone.
"""

import re

__all__ = ["is_operational_noise", "is_action_log_conclusion"]

# A leading bracketed harness/operational tag, e.g. "[Tool]", "[Tool Result]",
# "[Git External]", "[Background Task: gilded-gauntlet]". The tag word(s) must
# be one of the known set and be immediately closed by "]" or ":...]" — this is
# what keeps "[Note] ..." and "[Tool tips]" from matching.
_NOISE_TAG_RE = re.compile(
    r"\["
    r"(?:tool|tool\s+result|tool\s+use|git\s+external|background\s+task|"
    r"system\s+reminder|hook)"
    r"(?::[^\]]*)?"
    r"\]",
    re.IGNORECASE,
)

# The WHOLE message is a single bare identifier token: a known prefixed id
# (toolu_…, tool_…, task_…, call_…, req_…, msg_…) or a UUID. Matched with
# fullmatch against the stripped content, so an id appearing inside a sentence
# is left to the soft custom-instructions guidance, not dropped here.
_ID_ONLY_RE = re.compile(
    r"(?:toolu|tool|task|call|req|msg)_[A-Za-z0-9_-]{6,}"
    r"|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)

# The WHOLE message is a control / handshake instruction. Kept deliberately
# tiny and anchored (fullmatch) to the known "say BEGIN…" family so legitimate
# prose like "Let's begin the design review." is never caught.
_HANDSHAKE_RE = re.compile(
    r"(?:please\s+)?say\s+begin(?:\s+and\s+then\s+stop)?\.?"
    r"|begin\s+now\.?",
    re.IGNORECASE,
)


# An "action-log" CONCLUSION (distinct from is_operational_noise, which screens
# input *messages*). The deriver sometimes records a routine, one-off
# tool/command/test/git/file-edit *execution* as if it were a durable fact —
# "claude ran `cargo check`", "deploy created commit 196c381", "edited foo.ts".
# Those carry no lasting signal about the peer and dilute retrieval. This matches
# the *shape* of such an event log, subject-agnostically (no hard-coded peer
# names), so it generalizes across peers/workspaces.
_ACTION_LOG_RE = re.compile(
    # "<action verb> ... <command / test / git / docker / slash-command>"
    r"\b(?:ran|re-?ran|executed|performed|issued|invoked)\b[^.]{0,40}"
    r"(?:`|\bcommand\b|\bcommands\b|\bcargo\b|\bnpm\b|\bpnpm\b|\bbun\b|\bpytest\b"
    r"|\bmake\b|\bgit\b|\bdocker\b|\bgh\b|\btests?\b|\btest suite\b|/[a-z][\w:-]*)"
    # "<action verb> ... git <subcommand>" — verb required, so durable prose like
    # "a rule about shared-checkout git status" never matches.
    r"|\b(?:ran|re-?ran|executed|performed|issued|switched|made|did)\b[^.]{0,30}"
    r"\bgit\s+(?:add|commit|push|pull|status|branch|checkout|switch|rebase|merge"
    r"|stash|init|clone|fetch|reset|rev-parse|log|diff)\b"
    # commit identified by hash
    r"|\bcommit\s+(?:with\s+hash\s+|hash\s+)?[0-9a-f]{7,40}\b"
    # explicit command/tool/script execution
    r"|\b(?:executed|invoked)\s+(?:the\s+|a\s+)?(?:command|tool|script|macro|test"
    r"|suite|hook)\b"
    r"|\bused\s+the\s+(?:command|tool|slash[\s-]?command)\b"
    # edited/created/etc. a concrete dotted filename
    r"|\b(?:edited|modified|wrote|created|deleted|renamed|moved)\b[^.]{0,50}"
    r"\b[\w./-]+\.[a-z]{1,6}\b",
    re.IGNORECASE,
)

# A conclusion that reads as a durable preference / standing rule / stable
# attribute is NEVER treated as an action-log, even if it uses an action verb
# ("deploy created a standing rule that…"). Protects high-value signal.
_DURABLE_GUARD_RE = re.compile(
    r"\b(?:prefer|preference|standing rule|standing instruction|doctrine|always"
    r"|never|AuDHD|communication style|wants?|instructed\s+(?:that|to)|requires?"
    r"|global rule|rule\s+(?:is|for|about|includes?|that|stating|:)|convention"
    r"|policy|values?|believes?|dislikes?|likes?|treated as)\b",
    re.IGNORECASE,
)


def is_action_log_conclusion(content: str | None) -> bool:
    """Return True if ``content`` is a routine action/execution log, not a fact.

    Catches the deriver's occasional habit of recording one-off tool/command/
    test/git/file-edit executions ("ran ``cargo check``", "git commit <hash>",
    "edited foo.ts") as conclusions. Subject-agnostic, so it works for any peer.
    A conclusion that also reads as a durable preference / standing rule / stable
    attribute is never flagged, even when it uses an action verb.
    """
    if not content:
        return False
    text = content.strip()
    if not text:
        return False
    if _DURABLE_GUARD_RE.search(text):
        return False
    return bool(_ACTION_LOG_RE.search(text))


def is_operational_noise(content: str | None) -> bool:
    """Return True if ``content`` is wholly operational noise (no substance).

    Conservative: only an empty body, a leading known harness tag, a bare
    id-token message, or a control handshake qualifies. A substantive message
    that merely mentions a path/stat/id does NOT.
    """
    if content is None:
        return True

    text = content.strip()
    if not text:
        return True

    # 1. Leading operational/harness tag (e.g. "[Tool] ...", "[Git External] ...").
    if _NOISE_TAG_RE.match(text):
        return True

    # 2. The entire message is a bare id token.
    if _ID_ONLY_RE.fullmatch(text):
        return True

    # 3. The entire message is a control/handshake phrase.
    return bool(_HANDSHAKE_RE.fullmatch(text))
