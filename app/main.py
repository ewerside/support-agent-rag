"""FastAPI app: the chat page and the /chat endpoint. Run: uvicorn app.main:app --reload"""

import logging
import secrets
import time
from collections import OrderedDict, defaultdict, deque

import anthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import config
from app.agent import answer

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
for noisy in ("httpx", "httpx2"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger(__name__)

# An even number keeps each user message with its reply when old messages drop off.
HISTORY_LIMIT = 10
MAX_SESSIONS = 1000
REQUESTS_PER_MINUTE = 20
STATIC_DIR = config.ROOT / "app" / "static"

app = FastAPI(title="Wrenfield Coffee Gear support agent")
# Kept in memory, oldest dropped first. History is text only: replaying old thinking blocks
# after trimming the history would be rejected by the API.
sessions: OrderedDict[str, dict] = OrderedDict()
recent_requests: defaultdict[str, deque] = defaultdict(deque)


class ChatRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=100)
    message: str = Field(min_length=1, max_length=4000)


def check_rate_limit(client_ip: str) -> None:
    now = time.monotonic()
    hits = recent_requests[client_ip]
    while hits and now - hits[0] > 60:
        hits.popleft()
    if len(hits) >= REQUESTS_PER_MINUTE:
        raise HTTPException(
            429, "Too many messages. Please wait a minute and try again."
        )
    hits.append(now)


def get_session(session_id: str | None) -> tuple[str, dict]:
    # The server issues session ids, so a client can't pick one and read another chat.
    if session_id in sessions:
        sessions.move_to_end(session_id)
        return session_id, sessions[session_id]
    return secrets.token_urlsafe(16), {
        "history": deque(maxlen=HISTORY_LIMIT),
        "ticket_id": None,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/chat")
def chat(request: ChatRequest, http_request: Request) -> dict:
    check_rate_limit(http_request.client.host if http_request.client else "unknown")
    session_id, session = get_session(request.session_id)
    user_message = {"role": "user", "content": request.message}
    try:
        result = answer(
            [*session["history"], user_message], open_ticket=session["ticket_id"]
        )
    except anthropic.APIError as exc:
        log.error("agent failed for session %s: %s", session_id, exc)
        raise HTTPException(
            502, "The assistant is not available right now. Please try again."
        ) from exc

    session["history"].extend(
        [user_message, {"role": "assistant", "content": result["reply"]}]
    )
    session["ticket_id"] = session["ticket_id"] or result["ticket_id"]
    sessions[session_id] = session
    if len(sessions) > MAX_SESSIONS:
        sessions.popitem(last=False)
    log.info(
        "session=%s tools=%s ticket=%s tokens=%s latency_ms=%s",
        session_id,
        [t["name"] for t in result["tools_called"]],
        result["ticket_id"],
        result["usage"],
        result["latency_ms"],
    )
    # Tool results and token counts stay on the server; the page only needs these.
    return {
        "session_id": session_id,
        "reply": result["reply"],
        "sources": result["sources"],
        "ticket_id": result["ticket_id"],
    }
