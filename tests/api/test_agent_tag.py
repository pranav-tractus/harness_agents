import pytest

from apps.api.services import agent_tag


@pytest.mark.parametrize(
    "body",
    [
        "hello there",
        "",
        "   ",
        "tell @agent about it later",   # tag must be at the start
        "@agentic drift",               # \b must not match mid-word
    ],
)
def test_untagged_bodies_return_none(body):
    assert agent_tag.parse(body) is None


@pytest.mark.parametrize(
    "body",
    [
        "@agent create sales order",
        "@AGENT create sales order",     # case-insensitive
        "   @agent draft it",            # leading whitespace stripped
        "@agent",                        # bare tag, no verb
        "@agent please confirm",         # confirm word is not the FIRST word
    ],
)
def test_tagged_without_leading_confirm_word_is_ask(body):
    assert agent_tag.parse(body) == "ask"


@pytest.mark.parametrize("word", ["confirm", "Finalize", "APPROVE"])
def test_leading_confirm_words_are_approve(word):
    assert agent_tag.parse(f"@agent {word}") == "approve"


def test_confirm_word_may_be_followed_by_more_text():
    assert agent_tag.parse("@agent confirm this order please") == "approve"
