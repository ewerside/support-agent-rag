"""The agent's three tools: their schemas for the Anthropic API and the code that runs them."""

import json
import logging
import re
from datetime import date
from decimal import Decimal
from functools import lru_cache

import httpx
import psycopg
from psycopg.rows import dict_row

import config
from app.retrieval import search

log = logging.getLogger(__name__)

HUBSPOT_API = "https://api.hubapi.com"
HUBSPOT_CONFIG = config.ROOT / "config" / "hubspot.json"
# HubSpot's built-in association type for ticket -> contact.
TICKET_TO_CONTACT = 16
NOT_FOUND = "not found"
ESCALATION_REASONS = [
    "human_requested",
    "refund_outside_policy",
    "charge_dispute",
    "legal_threat",
    "upset_customer",
    "unanswered_question",
]

TOOLS = [
    {
        "name": "search_kb",
        "description": (
            "Search the Wrenfield Coffee Gear help center. Returns the 5 most relevant passages, "
            "each with the title of its article. Use it for every question about shipping, returns, "
            "warranty, orders, subscriptions, payments, products or contacting the store."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to look for, as a short question or phrase in English.",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_order",
        "description": (
            "Look up one order. Needs the order number (like WCG-10001) and the email the customer "
            "used at checkout. Returns the order only when both match. Otherwise returns "
            "'not found', without saying which one was wrong."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "Order number, like WCG-10001.",
                },
                "email": {"type": "string", "description": "Email used at checkout."},
            },
            "required": ["order_id", "email"],
            "additionalProperties": False,
        },
    },
    {
        "name": "escalate",
        "description": (
            "Hand the conversation to a person on the support team by opening a ticket in HubSpot. "
            "Returns the ticket id. The team replies to the customer by email."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "enum": ESCALATION_REASONS},
                "summary": {
                    "type": "string",
                    "description": (
                        "What the customer needs and what you already tried, in 2 to 4 sentences, "
                        "so the team doesn't have to ask again. Include any order number. Call "
                        "them 'the customer', not he or she."
                    ),
                },
                "customer_email": {
                    "type": "string",
                    "description": "Email to reply to.",
                },
            },
            "required": ["reason", "summary", "customer_email"],
            "additionalProperties": False,
        },
    },
]


def search_kb(query: str) -> list[dict]:
    return [
        {"id": r["id"], "title": r["title"], "content": r["content"]}
        for r in search(query, k=5)
    ]


def normalize_order_id(order_id: str) -> str:
    # Customers type "wcg10001", "#10001" or "WCG 10001"; the number is what matters.
    # Take the whole number, so a typo like 100201 isn't cut down to an order that exists.
    digits = re.search(r"(?<!\d)\d{5,}(?!\d)", order_id)
    return f"WCG-{digits.group(0)}" if digits else order_id.strip().upper()


def get_order(order_id: str, email: str) -> dict | str:
    """Return the order only when the number and the email match the same order."""
    with psycopg.connect(
        config.DATABASE_URL, connect_timeout=10, row_factory=dict_row
    ) as conn:
        # One query for both checks, so a wrong email and a wrong number look exactly the same.
        row = conn.execute(
            "select order_id, customer_name, country, status, carrier, tracking_number, "
            "shipped_at, eta, items, total, currency from support_agent.orders "
            "where order_id = %s and lower(email) = lower(%s)",
            (normalize_order_id(order_id), email.strip()),
        ).fetchone()
    if row is None:
        return NOT_FOUND
    return {k: str(v) if isinstance(v, date | Decimal) else v for k, v in row.items()}


@lru_cache(maxsize=1)
def _hubspot_settings() -> dict:
    if not HUBSPOT_CONFIG.exists():
        raise RuntimeError(
            f"{HUBSPOT_CONFIG.name} is missing. Run: python -m scripts.setup_hubspot"
        )
    return json.loads(HUBSPOT_CONFIG.read_text(encoding="utf-8"))


def _hubspot(method: str, path: str, body: dict) -> dict:
    headers = {"Authorization": f"Bearer {config.HUBSPOT_TOKEN}"}
    response = httpx.request(
        method, f"{HUBSPOT_API}{path}", headers=headers, json=body, timeout=15
    )
    if response.is_error:
        raise RuntimeError(
            f"HubSpot {path} -> {response.status_code}: {response.text[:300]}"
        )
    try:
        return response.json()
    except ValueError:
        raise RuntimeError(f"HubSpot {path} returned a body that isn't JSON") from None


def _find_contact(email: str) -> str | None:
    body = {
        "filterGroups": [
            {"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}
        ],
        "limit": 1,
    }
    results = _hubspot("POST", "/crm/v3/objects/contacts/search", body)["results"]
    return results[0]["id"] if results else None


def escalate(reason: str, summary: str, customer_email: str) -> dict:
    """Open a HubSpot ticket, linked to the contact with this email if one exists."""
    settings = _hubspot_settings()
    email = customer_email.strip()
    body = {
        "properties": {
            "subject": f"Chat escalation: {reason.replace('_', ' ')} ({email or 'no email'})",
            "content": f"{summary}\n\nCustomer email, typed in the chat and not verified: "
            f"{email or 'not given'}",
            "hs_pipeline": settings["pipeline_id"],
            "hs_pipeline_stage": settings["stage_id"],
        }
    }
    try:
        contact_id = _find_contact(email) if email else None
    except (httpx.HTTPError, RuntimeError) as exc:
        # The link to a contact is a nice-to-have. The customer still gets a ticket.
        log.warning(
            "contact search failed, opening the ticket without a contact: %s", exc
        )
        contact_id = None
    if contact_id:
        body["associations"] = [
            {
                "to": {"id": contact_id},
                "types": [
                    {
                        "associationCategory": "HUBSPOT_DEFINED",
                        "associationTypeId": TICKET_TO_CONTACT,
                    }
                ],
            }
        ]
    ticket = _hubspot("POST", "/crm/v3/objects/tickets", body)
    return {"ticket_id": ticket["id"], "linked_contact": contact_id is not None}


def run_tool(name: str, args: dict) -> tuple[str, bool]:
    """Run a tool call from the model. Returns (result as text, is_error)."""
    try:
        if name == "search_kb":
            result = search_kb(args["query"])
        elif name == "get_order":
            result = get_order(args["order_id"], args["email"])
        elif name == "escalate":
            result = escalate(args["reason"], args["summary"], args["customer_email"])
        else:
            return f"Unknown tool {name!r}. Use search_kb, get_order or escalate.", True
    except (psycopg.Error, httpx.HTTPError, RuntimeError) as exc:
        # The details stay in the log. The model only learns that the tool failed, so it can
        # say so instead of guessing, and can't repeat hostnames or API errors to the customer.
        log.error("tool %s failed: %s", name, exc)
        return f"The {name} tool isn't working right now. Don't guess the answer.", True
    return json.dumps(result), False
