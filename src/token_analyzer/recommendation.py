from __future__ import annotations

import bisect
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import duckdb

from .core import EXCLUDED_ANALYSIS_WORDS, _filter_clause, normalize_term


WEIGHT_MODES: dict[str, dict[str, float]] = {
    "balanced": {
        "orders": 0.35,
        "clicks": 0.25,
        "impressions": 0.10,
        "cvr": 0.15,
        "ctr": 0.10,
        "frequency": 0.05,
    },
    "traffic": {
        "orders": 0.20,
        "clicks": 0.35,
        "impressions": 0.20,
        "cvr": 0.05,
        "ctr": 0.15,
        "frequency": 0.05,
    },
    "conversion": {
        "orders": 0.40,
        "clicks": 0.15,
        "impressions": 0.05,
        "cvr": 0.25,
        "ctr": 0.10,
        "frequency": 0.05,
    },
}

WEIGHT_KEYS = ("orders", "clicks", "impressions", "cvr", "ctr", "frequency")


@dataclass(frozen=True)
class RecommendationCandidate:
    text: str
    kind: str
    frequency: int
    impressions: int
    clicks: int
    orders: int
    ctr: float | None
    cvr: float | None
    smoothed_ctr: float
    smoothed_cvr: float
    score: float


@dataclass(frozen=True)
class RecommendationCandidates:
    scope_query: str
    mode: str
    record_count: int
    words: list[RecommendationCandidate]
    phrases: list[RecommendationCandidate]
    filter_summary: str = ""


def _candidate_terms(tokens: list[str]) -> tuple[set[str], set[str]]:
    words = {token for token in tokens if token and token not in EXCLUDED_ANALYSIS_WORDS}
    phrases: set[str] = set()
    for size in (2, 3):
        for start in range(0, len(tokens) - size + 1):
            phrase_tokens = tokens[start : start + size]
            if not any(token in EXCLUDED_ANALYSIS_WORDS for token in phrase_tokens):
                phrases.add(" ".join(phrase_tokens))
    return words, phrases


def _add_metrics(
    target: dict[str, list[float]],
    terms: Iterable[str],
    impressions: float,
    clicks: float,
    orders: float,
) -> None:
    for term in terms:
        values = target.setdefault(term, [0.0, 0.0, 0.0, 0.0])
        values[0] += 1
        values[1] += impressions
        values[2] += clicks
        values[3] += orders


def _percentile(values: list[float], value: float) -> float:
    if len(values) <= 1:
        return 1.0
    position = bisect.bisect_right(values, value) - 1
    return position / (len(values) - 1)


def _score_candidates(
    aggregates: dict[str, list[float]],
    kind: str,
    weights: dict[str, float],
    prior_ctr: float,
    prior_cvr: float,
    limit: int,
) -> list[RecommendationCandidate]:
    prepared: list[dict[str, float | str]] = []
    for text, (frequency, impressions, clicks, orders) in aggregates.items():
        smoothed_ctr = (clicks + prior_ctr * 1000) / (impressions + 1000)
        smoothed_cvr = (orders + prior_cvr * 20) / (clicks + 20)
        prepared.append(
            {
                "text": text,
                "frequency": frequency,
                "impressions": impressions,
                "clicks": clicks,
                "orders": orders,
                "ctr": clicks / impressions if impressions else 0.0,
                "cvr": orders / clicks if clicks else 0.0,
                "smoothed_ctr": smoothed_ctr,
                "smoothed_cvr": smoothed_cvr,
            }
        )

    if not prepared:
        return []

    ranked_values = {
        metric: sorted(float(row[metric]) for row in prepared)
        for metric in ("orders", "clicks", "impressions", "smoothed_cvr", "smoothed_ctr", "frequency")
    }
    score_metric = {"cvr": "smoothed_cvr", "ctr": "smoothed_ctr"}
    results: list[RecommendationCandidate] = []
    for row in prepared:
        score = 0.0
        for weight_name, weight in weights.items():
            metric_name = score_metric.get(weight_name, weight_name)
            metric_value = float(row[metric_name])
            score += weight * _percentile(ranked_values[metric_name], metric_value)
        impressions = float(row["impressions"])
        clicks = float(row["clicks"])
        orders = float(row["orders"])
        results.append(
            RecommendationCandidate(
                text=str(row["text"]),
                kind=kind,
                frequency=int(row["frequency"]),
                impressions=int(round(impressions)),
                clicks=int(round(clicks)),
                orders=int(round(orders)),
                ctr=clicks / impressions if impressions else None,
                cvr=orders / clicks if clicks else None,
                smoothed_ctr=float(row["smoothed_ctr"]),
                smoothed_cvr=float(row["smoothed_cvr"]),
                score=round(score * 100, 2),
            )
        )

    results.sort(
        key=lambda item: (
            item.score,
            item.orders,
            item.clicks,
            item.frequency,
            item.text,
        ),
        reverse=True,
    )
    return results[:limit]


def get_recommendation_candidates(
    database_path: str | Path,
    mode: str = "balanced",
    scope_query: str = "",
    limit_per_kind: int = 40,
    custom_weights: dict[str, float] | None = None,
    filters: Mapping[str, str] | None = None,
) -> RecommendationCandidates:
    database = Path(database_path)
    if not database.exists():
        raise ValueError("请先导入Excel")
    if mode != "custom" and mode not in WEIGHT_MODES:
        raise ValueError("不支持的推荐模式")
    if mode == "custom":
        if custom_weights is None or set(custom_weights) != set(WEIGHT_KEYS):
            raise ValueError("请先设置完整的自定义权重")
        if any(value < 0 for value in custom_weights.values()):
            raise ValueError("自定义权重不能小于0")
        if abs(sum(custom_weights.values()) - 1.0) > 0.0001:
            raise ValueError("自定义权重合计必须为100%")

    normalized_scope = normalize_term(scope_query)
    filter_clause, filter_parameters = _filter_clause(filters)
    parameters: list[object] = list(filter_parameters)
    where_clause = f"WHERE 1 = 1{filter_clause}"
    if normalized_scope:
        where_clause += " AND (' ' || records.search_term || ' ') LIKE ?"
        parameters.append(f"% {normalized_scope} %")

    words: dict[str, list[float]] = {}
    phrases: dict[str, list[float]] = {}
    record_count = 0
    total_impressions = 0.0
    total_clicks = 0.0
    total_orders = 0.0
    connection = duckdb.connect(str(database), read_only=True)
    try:
        cursor = connection.execute(
            f"""
            SELECT records.search_term, records.impressions, records.clicks, records.orders
            FROM search_records AS records
            {where_clause}
            """,
            parameters,
        )
        while True:
            rows = cursor.fetchmany(10_000)
            if not rows:
                break
            for search_term, impressions, clicks, orders in rows:
                record_count += 1
                row_impressions = float(impressions or 0)
                row_clicks = float(clicks or 0)
                row_orders = float(orders or 0)
                total_impressions += row_impressions
                total_clicks += row_clicks
                total_orders += row_orders
                row_words, row_phrases = _candidate_terms(str(search_term).split())
                _add_metrics(words, row_words, row_impressions, row_clicks, row_orders)
                _add_metrics(phrases, row_phrases, row_impressions, row_clicks, row_orders)
    finally:
        connection.close()

    if record_count == 0:
        if normalized_scope:
            raise ValueError("当前搜索范围没有可推荐的数据")
        raise ValueError("当前数据为空，请重新导入Excel")

    prior_ctr = total_clicks / total_impressions if total_impressions else 0.0
    prior_cvr = total_orders / total_clicks if total_clicks else 0.0
    weights = custom_weights if mode == "custom" else WEIGHT_MODES[mode]
    return RecommendationCandidates(
        scope_query=normalized_scope,
        mode=mode,
        record_count=record_count,
        words=_score_candidates(words, "word", weights, prior_ctr, prior_cvr, limit_per_kind),
        phrases=_score_candidates(phrases, "phrase", weights, prior_ctr, prior_cvr, limit_per_kind),
        filter_summary="、".join(str(value) for value in (filters or {}).values() if str(value).strip()),
    )
