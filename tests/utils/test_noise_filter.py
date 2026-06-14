"""Unit tests for src.utils.noise_filter.is_operational_noise.

The classifier is deliberately conservative: it must catch wholly-operational
messages while never dropping substantive content that merely *mentions* a
path, stat, or id. The NEGATIVE cases below are the load-bearing ones.
"""

import pytest

from src.utils.noise_filter import is_action_log_conclusion, is_operational_noise

# Messages that ARE wholly operational noise -> should be filtered (True).
NOISE_CASES = [
    # empty / whitespace
    "",
    "   ",
    "\n\t  \n",
    None,
    # leading harness tags
    "[Tool] read /opt/foundry/data/world.json",
    "[Tool Result] {ok: true}",
    "[Tool Use] grep -rn foo",
    "[Git External] origin/main advanced by 3 commits",
    "[Background Task] gilded-gauntlet import finished",
    "[Background Task: reliquary-crawl] done",
    "[System Reminder] you have 5 tasks pending",
    "[Hook] user-prompt-submit fired",
    "  [Tool] leading whitespace still matches",
    "[TOOL] case insensitive",
    # bare id tokens (entire message)
    "toolu_01A09q90qw90lq917835lq9",
    "task_7f3a9b2c1d",
    "call_abc123def456",
    "msg_0001hZ2k9",
    "550e8400-e29b-41d4-a716-446655440000",
    # control / handshake phrases
    "say BEGIN and then stop",
    "Say BEGIN and then stop.",
    "please say begin",
    "begin now",
]

# Messages that are SUBSTANTIVE -> must NOT be filtered (False). These guard
# against over-eager matching that would silently drop real representation data.
SUBSTANTIVE_CASES = [
    # mentions a tmp path but is real content
    "I edited /tmp/honcho-custom-instructions.json to set the deriver guidance.",
    "The fix writes the export to /tmp/out.json before validating it.",
    # mentions a stat/percentage but is real content
    "CPU hit 95% during the gilded-gauntlet import — worth profiling the deriver.",
    "Memory sat around 768m, well under the 1g cap.",
    # contains an id mid-sentence (not the whole message)
    "The tool call toolu_01A09 failed because the bridge was offline.",
    "Reference task_7f3a in the follow-up issue.",
    # brackets that are NOT operational tags
    "[Note] remember to import the whole class, not a truncated one.",
    "[Design] spine + adapters keeps Foundry churn at the edge.",
    "[Tool tips for cooking] are off-topic here.",
    # 'begin' used as ordinary prose, not a handshake
    "Let's begin the design review of the conclusion-retrieval path.",
    "We begin now by forking the Honcho server into ~/workspace.",
    # short but real
    "done",
    "yes, ship it",
    # a git mention that is real prose (not a [Git External] tag)
    "git status shows the fixtures dir is dirty from a parallel session.",
    # looks idish but is part of a sentence with surrounding words
    "The UUID 550e8400-e29b-41d4-a716-446655440000 belongs to the test actor.",
]


@pytest.mark.parametrize("content", NOISE_CASES)
def test_operational_noise_is_filtered(content: str | None):
    assert is_operational_noise(content) is True


@pytest.mark.parametrize("content", SUBSTANTIVE_CASES)
def test_substantive_content_is_kept(content: str):
    assert is_operational_noise(content) is False


# Derived CONCLUSIONS that are routine action/execution logs -> drop (True).
ACTION_LOG_CASES = [
    "On June 3, 2026 at 04:11:10, claude ran `cargo check` and it succeeded.",
    "claude ran a full test suite of 339 tests, all green.",
    "On June 7, 2026, deploy created a new Git commit with hash 196c381.",
    "commit 6d1fa7f referenced a documentation-only change.",
    "On May 26, 2026, deploy used the command '/improve-codebase-architecture'.",
    "deploy issued the command '/honcho:status' at 17:39:42 UTC.",
    "claude ran git add for web/src/stores/moderation-store.ts.",
    "On June 7, 2026, deploy switched the git branch from feat/x to main.",
    "claude executed the command `docker exec honcho-db psql -U honcho`.",
    "claude edited mute-rule-repo.ts changing the select clause to insert.",
]

# Conclusions that are DURABLE facts and must survive (False) even though they
# use action verbs or mention git/commands/filenames. These are the load-bearing
# regression guards — dropping any of them is a real signal loss.
DURABLE_CONCLUSION_CASES = [
    # the two false positives caught during live precision tuning
    "claude's global rule includes a caution about shared-checkout git status.",
    "deploy wants agents.md treated as inside the server boundary.",
    # core identity / preferences
    "deploy has AuDHD and generally prefers bullet points for responses.",
    "deploy's communication style is conversational but direct on important details.",
    "deploy prefers concise, direct responses with clear visual separation.",
    # standing rules / conventions (use action verbs but are durable)
    "deploy created a standing rule that PRs must be green before merge.",
    "deploy's standing rule: always inspect the token actor, not the base actor.",
    "The convention is to keep the Issue Map in sync with every merged PR.",
    # a bare git mention in prose, no execution frame
    "git status shows the fixtures dir is dirty from a parallel session.",
    "deploy dislikes losing signal to over-eager filters.",
]


@pytest.mark.parametrize("content", ACTION_LOG_CASES)
def test_action_log_conclusion_is_filtered(content: str):
    assert is_action_log_conclusion(content) is True


@pytest.mark.parametrize("content", DURABLE_CONCLUSION_CASES)
def test_durable_conclusion_is_kept(content: str):
    assert is_action_log_conclusion(content) is False


@pytest.mark.parametrize("content", ["", "   ", None])
def test_action_log_empty_is_not_flagged(content: str | None):
    # empty/None carries no action — not our concern (returns False, unlike the
    # operational-noise classifier which treats empty as noise).
    assert is_action_log_conclusion(content) is False
