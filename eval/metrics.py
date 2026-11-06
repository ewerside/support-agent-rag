"""Evaluation metrics as plain functions over per-case results."""

from statistics import mean


def unique(items: list[str]) -> list[str]:
    """Drop repeats but keep the order, so several chunks from one article count once."""
    return list(dict.fromkeys(items))


def average_precision(relevant: set[str], retrieved: list[str]) -> float:
    """Average precision with the same definition as avg_p in github.com/ewerside/Map-K (main.py).

    Walk the retrieved list in order and, at each relevant hit, record hits so far divided by
    the position. The sum is divided by the number of relevant items, so a relevant article
    that was not retrieved lowers the score. The caller passes a list already cut to the top k.
    """
    hits = 0
    precisions = []
    for position, item in enumerate(retrieved, 1):
        if item in relevant:
            hits += 1
            precisions.append(hits / position)
    return sum(precisions) / len(relevant)


def map_at_k(cases: list[tuple[set[str], list[str]]], k: int = 5) -> float:
    """Mean of average_precision over cases of (relevant set, ranked retrieved list)."""
    return mean(
        average_precision(relevant, retrieved[:k]) for relevant, retrieved in cases
    )


def hit_at_k(cases: list[tuple[set[str], list[str]]], k: int = 5) -> float:
    """Share of cases with at least one relevant item in the top k."""
    return mean(bool(relevant & set(retrieved[:k])) for relevant, retrieved in cases)


def precision_recall(predicted: list[bool], actual: list[bool]) -> tuple[float, float]:
    true_pos = sum(p and a for p, a in zip(predicted, actual))
    false_pos = sum(p and not a for p, a in zip(predicted, actual))
    false_neg = sum(a and not p for p, a in zip(predicted, actual))
    precision = true_pos / (true_pos + false_pos) if true_pos + false_pos else 0.0
    recall = true_pos / (true_pos + false_neg) if true_pos + false_neg else 0.0
    return precision, recall
