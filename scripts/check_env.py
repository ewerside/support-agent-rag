"""Check that each external service answers. Run: python -m scripts.check_env [service ...]"""

import sys

import anthropic
import httpx
import psycopg

import config

HUBSPOT_API = "https://api.hubapi.com"


def check_anthropic() -> str:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    try:
        message = client.messages.create(
            model=config.AGENT_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": "Reply with the word OK."}],
        )
    except anthropic.NotFoundError as exc:
        names = ", ".join(m.id for m in client.models.list())
        raise RuntimeError(
            f"model {config.AGENT_MODEL} not found. Current models: {names}"
        ) from exc
    text = "".join(b.text for b in message.content if b.type == "text").strip()
    return f"{message.model} replied {text!r}"


def check_supabase() -> str:
    with psycopg.connect(config.DATABASE_URL, connect_timeout=10) as conn:
        conn.execute("select 1").fetchone()
        try:
            conn.execute("create extension if not exists vector")
        except psycopg.errors.InsufficientPrivilege as exc:
            raise RuntimeError(
                "no permission to create the vector extension. "
                "Turn it on in Supabase: Database > Extensions > vector."
            ) from exc
        row = conn.execute(
            "select extversion from pg_extension where extname = 'vector'"
        ).fetchone()
    return f"select 1 ok, pgvector {row[0]}"


def _hubspot(client: httpx.Client, method: str, path: str, **kwargs) -> dict:
    response = client.request(method, path, **kwargs)
    if response.is_error:
        # HubSpot puts the useful part (missing scope, bad property) in the body.
        raise RuntimeError(
            f"{method} {path} -> {response.status_code}: {response.text[:300]}"
        )
    return response.json() if response.content else {}


def check_hubspot() -> str:
    headers = {"Authorization": f"Bearer {config.HUBSPOT_TOKEN}"}
    with httpx.Client(base_url=HUBSPOT_API, headers=headers, timeout=15) as client:
        portal = str(_hubspot(client, "GET", "/account-info/v3/details")["portalId"])
        if portal != config.HUBSPOT_PORTAL_ID:
            raise RuntimeError(
                f"token belongs to portal {portal}, but HUBSPOT_PORTAL_ID is {config.HUBSPOT_PORTAL_ID}"
            )
        pipeline = _hubspot(client, "GET", "/crm/v3/pipelines/tickets")["results"][0]
        stage = min(pipeline["stages"], key=lambda s: s["displayOrder"])
        ticket = _hubspot(
            client,
            "POST",
            "/crm/v3/objects/tickets",
            json={
                "properties": {
                    "subject": "check_env test ticket",
                    "content": "Created by scripts/check_env.py and deleted right after.",
                    "hs_pipeline": pipeline["id"],
                    "hs_pipeline_stage": stage["id"],
                }
            },
        )
        _hubspot(client, "DELETE", f"/crm/v3/objects/tickets/{ticket['id']}")
    return f"portal {portal}, ticket {ticket['id']} created and deleted"


CHECKS = {
    "anthropic": check_anthropic,
    "supabase": check_supabase,
    "hubspot": check_hubspot,
}

# Failures we expect from config, the network or each API. Anything else is a bug and should crash.
EXPECTED_ERRORS = (RuntimeError, anthropic.APIError, psycopg.Error, httpx.HTTPError)


def main(names: list[str]) -> int:
    unknown = [n for n in names if n not in CHECKS]
    if unknown:
        print(f"unknown service: {', '.join(unknown)}. Options: {', '.join(CHECKS)}")
        return 2
    failed = 0
    for name in names or CHECKS:
        # Report every service, not just the first failure, so one run shows what is missing.
        try:
            print(f"{name}: ok ({CHECKS[name]()})")
        except EXPECTED_ERRORS as exc:
            failed += 1
            print(f"{name}: FAIL ({type(exc).__name__}: {exc})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
