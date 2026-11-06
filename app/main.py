"""FastAPI app: the chat page and the /chat endpoint. Run: uvicorn app.main:app --reload"""

import logging
from collections import defaultdict, deque

import anthropic
from fastapi import FastAPI, HTTPException
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
STATIC_DIR = config.ROOT / "app" / "static"

app = FastAPI(title="Wrenfield Coffee Gear support agent")
# Text only: replaying old thinking blocks after trimming the history would be rejected by the API.
sessions: dict[str, deque] = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=4000)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    history = sessions[request.session_id]
    user_message = {"role": "user", "content": request.message}
    try:
        result = answer([*history, user_message])
    except anthropic.APIError as exc:
        log.error("agent failed for session %s: %s", request.session_id, exc)
        raise HTTPException(
            502, "The assistant is not available right now. Please try again."
        ) from exc
    history.append(user_message)
    history.append({"role": "assistant", "content": result["reply"]})
    log.info(
        "session=%s tools=%s ticket=%s tokens=%s latency_ms=%s",
        request.session_id,
        [t["name"] for t in result["tools_called"]],
        result["ticket_id"],
        result["usage"],
        result["latency_ms"],
    )
    return result
