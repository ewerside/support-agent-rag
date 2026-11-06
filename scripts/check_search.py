"""Quick search check: obvious questions must find their article in the top 3. Run: python -m scripts.check_search"""

import sys

from app.retrieval import search

TOP = 3
# One obvious question per category.
CASES = [
    ("How much does shipping to Canada cost?", "shipping-canada"),
    ("How do I return an item I bought?", "returns-how-to"),
    ("How long is the warranty on an espresso machine?", "warranty-coverage"),
    ("How do I pause my coffee subscription?", "subscription-pause-skip"),
    ("How do I descale my espresso machine?", "products-descale"),
]


def main() -> int:
    failed = 0
    print(f"{'question':<52} {'expected article':<26} position  top {TOP} chunks")
    for question, expected in CASES:
        results = search(question, k=5)
        articles = [r["article_id"] for r in results]
        position = articles.index(expected) + 1 if expected in articles else None
        ok = position is not None and position <= TOP
        failed += not ok
        top = ", ".join(r["id"] for r in results[:TOP])
        print(
            f"{question:<52} {expected:<26} {position or '-':<9} {top}{'' if ok else '  FAIL'}"
        )
    print(f"{len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
