"""Check the help center articles against kb/facts.yaml. Run: python -m scripts.check_kb"""

import re
import sys
from pathlib import Path

import yaml

import config

KB_DIR = config.ROOT / "kb"
EXPECTED_ARTICLES = 40
MIN_SHARED_FACTS = 5
WORD_RANGE = (150, 500)
CATEGORIES = {
    "shipping",
    "returns",
    "warranty",
    "orders",
    "subscription",
    "payments",
    "products",
    "contact",
}
# Built with chr() so the formatter doesn't turn them into literal dashes in this file.
DASHES = (chr(0x2013), chr(0x2014))
BANNED_WORDS = re.compile(
    r"\b(seamless|robust|leverage|powerful|cutting-edge|delve|streamline|elevate|"
    r"comprehensive|effortless|game-changer|unlock|harness)\w*",
    re.IGNORECASE,
)
# Numbers that carry a policy or an instruction: money, clock times, durations, percentages, measures.
QUANTITY = re.compile(
    r"(?:C\$|\$|£)\d+(?:,\d{3})*(?:\.\d+)?"
    r"|\d{1,2} ?[ap]m(?: to \d{1,2} ?[ap]m)?"
    r"|\d+(?:\.\d+)?(?:(?:, | to | or )\d+(?:\.\d+)?)* (?:business )?"
    r"(?:second|minute|hour|day|week|month|year)s?\b"
    r"|\d+(?:\.\d+)?%"
    r"|\d+(?:\.\d+)? ?(?:kg|lb|g|mm|ml|liters?)\b",
    re.IGNORECASE,
)


def quantities(text: str) -> set[str]:
    return {" ".join(m.group(0).lower().split()) for m in QUANTITY.finditer(text)}


def has_value(value: str, text: str) -> bool:
    # Compare numbers as whole tokens, so "5 business days" doesn't match inside "3 to 5 business days".
    wanted = quantities(value)
    if wanted:
        return wanted <= quantities(text)
    return value.lower() in text.lower()


def load_articles(errors: list[str]) -> dict[str, str]:
    """Return the full text of each article by id, recording format problems in errors."""
    articles = {}
    for path in sorted((KB_DIR / "articles").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        parts = text.split("---\n", 2)
        if len(parts) != 3 or parts[0]:
            errors.append(f"{path.name}: missing frontmatter")
            continue
        meta = yaml.safe_load(parts[1]) or {}
        body = parts[2]
        check_article(path, meta, text, body, errors)
        articles[path.stem] = text
    return articles


def check_article(
    path: Path, meta: dict, text: str, body: str, errors: list[str]
) -> None:
    if meta.get("id") != path.stem:
        errors.append(
            f"{path.name}: id {meta.get('id')!r} does not match the file name"
        )
    if not meta.get("title"):
        errors.append(f"{path.name}: missing title")
    if meta.get("category") not in CATEGORIES:
        errors.append(f"{path.name}: bad category {meta.get('category')!r}")
    words = len(body.split())
    if not WORD_RANGE[0] <= words <= WORD_RANGE[1]:
        errors.append(
            f"{path.name}: {words} words, expected {WORD_RANGE[0]} to {WORD_RANGE[1]}"
        )
    for line_no, line in enumerate(text.splitlines(), 1):
        if any(d in line for d in DASHES):
            errors.append(f"{path.name}:{line_no}: has an em or en dash")
        for match in BANNED_WORDS.finditer(line):
            errors.append(f"{path.name}:{line_no}: banned word {match.group(0)!r}")


def main() -> int:
    errors: list[str] = []
    facts_text = (KB_DIR / "facts.yaml").read_text(encoding="utf-8")
    if any(d in facts_text for d in DASHES):
        errors.append("facts.yaml: has an em or en dash")
    facts = yaml.safe_load(facts_text)
    articles = load_articles(errors)
    if len(articles) != EXPECTED_ARTICLES:
        errors.append(f"{len(articles)} articles, expected {EXPECTED_ARTICLES}")

    allowed = set().union(*(quantities(f["text"]) for f in facts))
    for art_id, text in articles.items():
        unknown = quantities(text) - allowed
        if unknown:
            errors.append(f"{art_id}.md: values not in facts.yaml: {sorted(unknown)}")

    shared = []
    print(f"{'fact':<22} articles with every value")
    for fact in facts:
        found = [
            a
            for a, text in articles.items()
            if all(has_value(v, text) for v in fact["values"])
        ]
        print(f"{fact['id']:<22} {', '.join(found) or '-'}")
        if not found:
            unused = [
                v
                for v in fact["values"]
                if not any(has_value(v, t) for t in articles.values())
            ]
            detail = f", never used: {unused}" if unused else ""
            errors.append(f"fact {fact['id']}: no article has all its values{detail}")
        if len(found) >= 2:
            shared.append(fact["id"])
    if len(shared) < MIN_SHARED_FACTS:
        errors.append(
            f"only {len(shared)} facts appear in two articles, expected {MIN_SHARED_FACTS}"
        )

    print(
        f"\n{len(articles)} articles, {len(facts)} facts, {len(shared)} in two or more articles: {', '.join(shared)}"
    )
    for error in errors:
        print(f"FAIL {error}")
    print("ok" if not errors else f"{len(errors)} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
