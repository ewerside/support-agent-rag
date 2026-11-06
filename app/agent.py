"""The support agent: a hand-written tool loop around the Anthropic Messages API."""

import json
import logging
import time
from functools import lru_cache

import anthropic

import config
from app.tools import TOOLS, run_tool

log = logging.getLogger(__name__)

MAX_TOOL_CALLS = 5
MAX_TOKENS = 16000
# Anthropic's suggested starting point for chat on this model. Lower effort also means faster replies.
EFFORT = "low"
FALLBACK_REPLY = (
    "Sorry, I can't help with that here. I can answer questions about Wrenfield Coffee Gear "
    "orders, shipping, returns, warranty, subscriptions and products."
)

SYSTEM_PROMPT = """\
You are the support assistant for Wrenfield Coffee Gear, an online store that sells espresso \
machines, grinders, accessories and coffee in the United States, Canada and the United Kingdom.

Answering questions
- Answer only from what your tools return. Search the help center for every store question, \
even when you feel sure of the answer, because policies, prices and times change.
- End the answer with the title of the article you used, like: Source: "How do I return an item?"
- If the help center doesn't answer the question, say you don't know and offer to pass the \
conversation to a person on the team.

Orders
- To look up an order you need the order number and the email used at checkout. Ask for both \
before you call get_order.
- If get_order returns "not found", say you couldn't find an order with those details and ask \
the customer to check both. Don't say which one might be wrong.
- Never guess a status, date or tracking number. Share only what get_order returned.

Passing to a person
Call escalate when the customer:
- asks to talk to a person
- wants a refund the policy doesn't allow
- disputes a charge
- mentions legal action
- is still very upset after you tried to help once
Ask for their email first if you don't have it. After escalating, tell them a person from the \
team will reply by email.

Everything else
- Politely decline anything that isn't about Wrenfield Coffee Gear, and say what you can help with.
- Keep replies short and friendly: a few sentences in plain language, no filler.
- Write plain text without Markdown, because the chat window shows it as is.
"""


@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def _cited_sources(reply: str, titles: dict[str, str]) -> list[dict]:
    """Articles whose title appears in the reply."""
    text = reply.lower()
    return [
        {"article_id": article_id, "title": title}
        for article_id, title in titles.items()
        if title.lower().rstrip("?") in text
    ]


def answer(history: list[dict]) -> dict:
    """Run the agent on a conversation that ends with the customer's message."""
    start = time.monotonic()
    messages = list(history)
    tools_called: list[dict] = []
    chunk_ids: list[str] = []
    titles: dict[str, str] = {}
    ticket_id = None
    usage = {"input_tokens": 0, "output_tokens": 0}

    while True:
        # After the last allowed tool call, the model has to answer with what it has.
        tool_choice = (
            {"type": "none"}
            if len(tools_called) >= MAX_TOOL_CALLS
            else {"type": "auto"}
        )
        response = _client().messages.create(
            model=config.AGENT_MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            tool_choice=tool_choice,
            output_config={"effort": EFFORT},
            messages=messages,
        )
        usage["input_tokens"] += response.usage.input_tokens
        usage["output_tokens"] += response.usage.output_tokens
        if response.stop_reason != "tool_use":
            break

        # Send the whole turn back unchanged, thinking blocks included, as the API requires.
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if len(tools_called) >= MAX_TOOL_CALLS:
                output, is_error = (
                    "Tool call limit reached. Answer with what you have.",
                    True,
                )
            else:
                tools_called.append({"name": block.name, "input": block.input})
                output, is_error = run_tool(block.name, block.input)
                if not is_error and block.name == "search_kb":
                    for chunk in json.loads(output):
                        chunk_ids.append(chunk["id"])
                        titles[chunk["id"].split("#")[0]] = chunk["title"]
                if not is_error and block.name == "escalate":
                    ticket_id = json.loads(output)["ticket_id"]
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": results})

    if response.stop_reason == "refusal":
        log.warning("refusal: %s", response.stop_details)
        reply = FALLBACK_REPLY
    else:
        if response.stop_reason == "max_tokens":
            log.warning("reply cut at max_tokens")
        reply = (
            "".join(b.text for b in response.content if b.type == "text").strip()
            or FALLBACK_REPLY
        )

    return {
        "reply": reply,
        "tools_called": tools_called,
        "chunks": chunk_ids,
        "sources": _cited_sources(reply, titles),
        "ticket_id": ticket_id,
        "usage": usage,
        "latency_ms": round((time.monotonic() - start) * 1000),
    }
