"""Chunk the help center articles, embed them and upsert into support_agent.kb_chunks. Run: python -m scripts.ingest"""

from pathlib import Path

import psycopg
import yaml

import config
from app.retrieval import embed_passages

ARTICLES_DIR = config.ROOT / "kb" / "articles"
MAX_WORDS = 350
OVERLAP = 50

UPSERT = """
insert into support_agent.kb_chunks (id, article_id, title, content, embedding)
values (%s, %s, %s, %s, %s::vector)
on conflict (id) do update set
    article_id = excluded.article_id,
    title = excluded.title,
    content = excluded.content,
    embedding = excluded.embedding
"""


def read_article(path: Path) -> tuple[dict, str]:
    _, front, body = path.read_text(encoding="utf-8").split("---\n", 2)
    return yaml.safe_load(front), body


def split_long(text: str) -> list[str]:
    words = text.split()
    if len(words) <= MAX_WORDS:
        return [text]
    step = MAX_WORDS - OVERLAP
    return [
        " ".join(words[i : i + MAX_WORDS]) for i in range(0, len(words) - OVERLAP, step)
    ]


def make_chunks() -> list[dict]:
    chunks = []
    for path in sorted(ARTICLES_DIR.glob("*.md")):
        meta, body = read_article(path)
        # v2: one chunk per article. In v1, splitting by section left out details the answer
        # needed from other sections of the same article. Long articles are still split.
        for i, block in enumerate(split_long(body.strip())):
            chunks.append(
                {
                    "id": f"{meta['id']}#{i}",
                    "article_id": meta["id"],
                    "title": meta["title"],
                    "content": block,
                }
            )
    return chunks


def main() -> None:
    chunks = make_chunks()
    # The title goes into the embedded text so a section like "## Timing" still knows its topic.
    vectors = embed_passages([f"{c['title']}\n{c['content']}" for c in chunks])
    rows = [
        (c["id"], c["article_id"], c["title"], c["content"], v)
        for c, v in zip(chunks, vectors)
    ]
    ids = [c["id"] for c in chunks]
    with psycopg.connect(config.DATABASE_URL, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.executemany(UPSERT, rows)
        # Drop chunks from sections or articles that no longer exist.
        stale = conn.execute(
            "delete from support_agent.kb_chunks where not (id = any(%s))", (ids,)
        ).rowcount
        (total,) = conn.execute(
            "select count(*) from support_agent.kb_chunks"
        ).fetchone()
    words = [len(c["content"].split()) for c in chunks]
    articles = len({c["article_id"] for c in chunks})
    print(
        f"{articles} articles -> {len(chunks)} chunks, {min(words)} to {max(words)} words each"
    )
    print(f"rows in kb_chunks: {total}, stale rows removed: {stale}")


if __name__ == "__main__":
    main()
