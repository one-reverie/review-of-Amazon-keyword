from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import duckdb
import pandas as pd


REQUIRED_COLUMNS = ("搜索词", "展示量", "点击量", "购买量")
OPTIONAL_COLUMNS = (
    "预算货币",
    "日期范围",
    "广告组合名称",
    "广告活动名称",
    "广告组名称",
    "总成本",
    "销售额",
)
SORT_EXPRESSIONS = {
    "search_term": "search_term",
    "clicks": "clicks",
    "impressions": "impressions",
    "orders": "orders",
    "ctr": "CASE WHEN impressions > 0 THEN clicks / impressions END",
    "cvr": "CASE WHEN clicks > 0 THEN orders / clicks END",
    "frequency": "frequency",
    "cost": "cost",
    "sales": "sales",
    "acos": "CASE WHEN sales > 0 THEN cost / sales END",
    "cpc": "CASE WHEN clicks > 0 THEN cost / clicks END",
}
FILTER_COLUMNS = {
    "date_range": "date_range",
    "currency": "currency",
    "portfolio": "portfolio",
    "campaign": "campaign",
    "ad_group": "ad_group",
}
ENGLISH_PREPOSITIONS = frozenset(
    {
        "about", "above", "across", "after", "against", "along", "among", "around",
        "as", "at", "before", "behind", "below", "beneath", "beside", "between",
        "beyond", "by", "despite", "down", "during", "except", "for", "from", "in",
        "inside", "into", "like", "near", "of", "off", "on", "onto", "opposite", "out",
        "outside", "over", "past", "per", "since", "through", "throughout", "till", "to",
        "toward", "towards", "under", "underneath", "unlike", "until", "up", "upon", "via",
        "with", "within", "without",
    }
)
GENDER_WORDS = frozenset(
    {
        "woman", "women", "womens", "women's", "female", "females", "lady", "ladies",
        "girl", "girls", "man", "men", "mens", "men's", "male", "males", "boy", "boys",
        "unisex", "damen", "herren", "frau", "frauen", "mann", "männer", "männern",
        "mujer", "mujeres", "hombre", "hombres", "niña", "niñas", "niño", "niños",
        "femme", "femmes", "homme", "hommes", "fille", "filles", "garçon", "garçons",
        "donna", "donne", "uomo", "uomini", "mulher", "mulheres", "homem", "homens",
        "レディース", "メンズ", "女士", "男士", "女性", "男性", "女款", "男款", "女", "男",
    }
)
EXCLUDED_ANALYSIS_WORDS = ENGLISH_PREPOSITIONS | GENDER_WORDS
_EXCLUDED_WORDS_SQL = ", ".join("'" + word.replace("'", "''") + "'" for word in sorted(EXCLUDED_ANALYSIS_WORDS))
HEADER_ALIASES = {
    "搜索词": ("搜索词", "搜索词条", "客户搜索词", "Search Term", "Customer Search Term"),
    "展示量": ("展示量", "曝光量", "Impressions"),
    "点击量": ("点击量", "点击", "Clicks"),
    "购买量": (
        "购买量", "订单量", "订单数", "Purchases", "Orders",
        "7 Day Total Orders (#)", "14 Day Total Orders (#)",
    ),
    "预算货币": ("预算货币", "币种", "Currency"),
    "日期范围": ("日期范围", "日期", "Date Range", "Date"),
    "广告组合名称": ("广告组合名称", "广告组合", "Portfolio Name", "Portfolio"),
    "广告活动名称": ("广告活动名称", "广告活动", "Campaign Name", "Campaign"),
    "广告组名称": ("广告组名称", "广告组", "Ad Group Name", "Ad Group"),
    "总成本": (
        "总成本", "成本", "花费", "支出", "广告花费", "广告费用", "Spend", "Cost",
        "Total Cost", "Ad Spend",
    ),
    "销售额": (
        "销售额", "总销售额", "广告销售额", "归因销售额", "成交金额", "销售金额",
        "Sales", "Total Sales", "Attributed Sales", "7天总销售额", "14天总销售额",
        "30天总销售额", "7 Day Total Sales", "14 Day Total Sales", "30 Day Total Sales",
    ),
}
_HEADER_ALIAS_LOOKUP = {
    unicodedata.normalize("NFKC", alias).casefold().strip(): canonical
    for canonical, aliases in HEADER_ALIASES.items()
    for alias in aliases
}
@dataclass(frozen=True)
class ImportResult:
    source_path: str
    imported_rows: int
    skipped_blank_terms: int


@dataclass(frozen=True)
class QueryResult:
    query: str
    total_items: int
    frequency: int
    impressions: int
    clicks: int
    orders: int
    ctr: float | None
    cvr: float | None
    cost: float | None
    sales: float | None
    acos: float | None
    cpc: float | None
    rows: list[dict[str, object]]


def normalize_term(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKC", str(value)).casefold().strip()
    return re.sub(r"\s+", " ", text)


def _normalize_header(value: object) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value)).casefold().strip())


def resolve_headers(raw_columns: Iterable[object]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    conflicts: dict[str, list[str]] = {}
    for column in raw_columns:
        canonical = _HEADER_ALIAS_LOOKUP.get(_normalize_header(column))
        if canonical is None:
            continue
        source_name = str(column)
        if canonical in resolved:
            conflicts.setdefault(canonical, [resolved[canonical]]).append(source_name)
        else:
            resolved[canonical] = source_name
    if conflicts:
        details = "；".join(
            f"{field}（{'、'.join(columns)}）" for field, columns in conflicts.items()
        )
        raise ValueError(f"字段映射冲突：{details}")
    missing = [name for name in REQUIRED_COLUMNS if name not in resolved]
    if missing:
        raise ValueError(f"缺少必需字段：{'、'.join(missing)}")
    return resolved


def _filter_clause(
    filters: Mapping[str, str] | None,
    alias: str = "records",
) -> tuple[str, list[object]]:
    conditions: list[str] = []
    parameters: list[object] = []
    for key, value in (filters or {}).items():
        selected = str(value).strip()
        if not selected:
            continue
        if key in FILTER_COLUMNS:
            conditions.append(f"{alias}.{FILTER_COLUMNS[key]} = ?")
            parameters.append(selected)
        elif key == "term_type":
            asin_expression = f"regexp_full_match({alias}.search_term, 'b0[a-z0-9]{{8}}')"
            conditions.append(asin_expression if selected == "ASIN" else f"NOT {asin_expression}")
    return (" AND " + " AND ".join(conditions) if conditions else "", parameters)


def _summary_filter_clause(
    row_filters: Mapping[str, Mapping[str, object]] | None,
    term_expression: str,
    metric_expressions: Mapping[str, str],
) -> tuple[str, list[object]]:
    conditions: list[str] = []
    parameters: list[object] = []
    for key, raw_spec in (row_filters or {}).items():
        spec = dict(raw_spec)
        if key == "search_term":
            contains = normalize_term(spec.get("contains", ""))
            if contains:
                conditions.append(f"contains(lower({term_expression}), ?)")
                parameters.append(contains)
            continue
        expression = metric_expressions.get(key)
        if expression is None:
            continue
        minimum = spec.get("min")
        maximum = spec.get("max")
        if minimum is not None:
            conditions.append(f"({expression}) >= ?")
            parameters.append(float(minimum))
        if maximum is not None:
            conditions.append(f"({expression}) <= ?")
            parameters.append(float(maximum))
    return (" HAVING " + " AND ".join(conditions) if conditions else "", parameters)


def _order_by_clause(
    sort_by: str,
    ascending: bool,
    sort_rules: Sequence[tuple[str, str]] | None,
) -> str:
    rules = list(sort_rules) if sort_rules is not None else [(sort_by, "asc" if ascending else "desc")]
    if not rules:
        rules = [("clicks", "desc")]
    seen: set[str] = set()
    parts: list[str] = []
    for key, direction in rules:
        if key not in SORT_EXPRESSIONS:
            raise ValueError("不支持的排序维度")
        normalized_direction = str(direction).casefold()
        if normalized_direction not in {"asc", "desc"}:
            raise ValueError("排序方向只能是升序或降序")
        if key in seen:
            raise ValueError("组合排序中的字段不能重复")
        seen.add(key)
        parts.append(f"{SORT_EXPRESSIONS[key]} {normalized_direction.upper()} NULLS LAST")
    if "search_term" not in seen:
        parts.append("search_term ASC")
    return ", ".join(parts)


def _term_match_clause(alias: str, terms: Iterable[str]) -> tuple[str, list[str]]:
    patterns = [
        "% " + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + " %"
        for term in terms
    ]
    if not patterns:
        raise ValueError("请输入要查询的词元或连续词组")
    condition = " OR ".join(
        f"(' ' || {alias}.search_term || ' ') LIKE ? ESCAPE '\\'"
        for _ in patterns
    )
    return f"({condition})", patterns


def get_filter_options(
    database_path: str | os.PathLike[str],
    filters: Mapping[str, str] | None = None,
) -> dict[str, list[str]]:
    database = Path(database_path)
    if not database.exists():
        raise ValueError("请先导入Excel")
    result: dict[str, list[str]] = {}
    connection = duckdb.connect(str(database), read_only=True)
    try:
        for key, column in FILTER_COLUMNS.items():
            related_filters = {name: value for name, value in (filters or {}).items() if name != key}
            filter_clause, parameters = _filter_clause(related_filters)
            rows = connection.execute(
                f"""
                SELECT DISTINCT records.{column}
                FROM search_records AS records
                WHERE records.{column} <> ''
                {filter_clause}
                ORDER BY records.{column}
                """,
                parameters,
            ).fetchall()
            result[key] = [str(row[0]) for row in rows]
        type_filters = {name: value for name, value in (filters or {}).items() if name != "term_type"}
        type_filter_clause, type_parameters = _filter_clause(type_filters)
        type_rows = connection.execute(
            f"""
            SELECT
                count(*) FILTER (WHERE regexp_full_match(search_term, 'b0[a-z0-9]{8}')),
                count(*) FILTER (WHERE NOT regexp_full_match(search_term, 'b0[a-z0-9]{8}'))
            FROM search_records AS records
            WHERE 1 = 1
            {type_filter_clause}
            """,
            type_parameters,
        ).fetchone()
        result["term_type"] = [
            label
            for label, count in zip(("关键词", "ASIN"), (type_rows[1], type_rows[0]))
            if int(count or 0) > 0
        ]
    finally:
        connection.close()
    return result


def _read_delimited_source(source: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    failures: list[str] = []
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        for separator in (",", "\t", ";"):
            try:
                header = pd.read_csv(source, encoding=encoding, sep=separator, nrows=0)
                resolved = resolve_headers(header.columns)
                frame = pd.read_csv(
                    source,
                    encoding=encoding,
                    sep=separator,
                    usecols=list(resolved.values()),
                )
                return frame, resolved
            except ValueError as exc:
                if str(exc).startswith("字段映射冲突："):
                    raise
                failures.append(str(exc))
            except (UnicodeDecodeError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
                failures.append(str(exc))
    detail = failures[-1] if failures else "无法识别文本编码或分隔符"
    raise ValueError(f"无法读取分隔文本：{detail}")


def _read_source(path: str | os.PathLike[str]) -> tuple[pd.DataFrame, int]:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        try:
            header = pd.read_excel(source, sheet_name=0, engine="calamine", nrows=0)
            resolved = resolve_headers(header.columns)
            frame = pd.read_excel(
                source,
                sheet_name=0,
                engine="calamine",
                usecols=list(resolved.values()),
            )
        except (OSError, ValueError) as exc:
            raise ValueError(f"无法读取第一个工作表：{exc}") from exc
    elif suffix in {".csv", ".txt"}:
        frame, resolved = _read_delimited_source(source)
    else:
        raise ValueError("仅支持.xlsx、.xlsm、.csv、.txt文件")

    frame = frame.rename(columns={source_name: canonical for canonical, source_name in resolved.items()})
    raw_rows = len(frame)
    frame["search_term"] = frame["搜索词"].map(normalize_term)
    frame = frame[frame["search_term"] != ""].copy()

    numeric_columns = {
        "展示量": "impressions",
        "点击量": "clicks",
        "购买量": "orders",
        "总成本": "cost",
        "销售额": "sales",
    }
    for source_name, target_name in numeric_columns.items():
        if source_name in frame.columns:
            frame[target_name] = pd.to_numeric(frame[source_name], errors="coerce").fillna(0)
        else:
            frame[target_name] = None

    text_columns = {
        "预算货币": "currency",
        "日期范围": "date_range",
        "广告组合名称": "portfolio",
        "广告活动名称": "campaign",
        "广告组名称": "ad_group",
    }
    for source_name, target_name in text_columns.items():
        if source_name in frame.columns:
            frame[target_name] = frame[source_name].fillna("").astype(str)
        else:
            frame[target_name] = ""

    columns = [
        "search_term",
        "currency",
        "date_range",
        "portfolio",
        "campaign",
        "ad_group",
        "impressions",
        "clicks",
        "orders",
        "cost",
        "sales",
    ]
    return frame[columns], raw_rows - len(frame)


def import_workbook(
    source_path: str | os.PathLike[str],
    database_path: str | os.PathLike[str],
) -> ImportResult:
    frame, skipped = _read_source(source_path)
    database = Path(database_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    staging = database.with_suffix(database.suffix + ".next")
    staging.unlink(missing_ok=True)

    connection = duckdb.connect(str(staging))
    try:
        connection.register("import_frame", frame)
        connection.execute(
            """
            CREATE TABLE search_records AS
            SELECT
                row_number() OVER ()::BIGINT AS record_id,
                search_term,
                currency,
                date_range,
                portfolio,
                campaign,
                ad_group,
                impressions::DOUBLE AS impressions,
                clicks::DOUBLE AS clicks,
                orders::DOUBLE AS orders,
                cost::DOUBLE AS cost,
                sales::DOUBLE AS sales
            FROM import_frame
            """
        )
        connection.execute("CREATE INDEX idx_search_term ON search_records(search_term)")
        connection.execute(
            f"""
            CREATE TABLE token_records AS
            SELECT DISTINCT records.record_id, parts.token
            FROM search_records AS records,
                 unnest(string_split(records.search_term, ' ')) AS parts(token)
            WHERE parts.token <> ''
              AND parts.token NOT IN ({_EXCLUDED_WORDS_SQL})
            """
        )
        connection.execute("CREATE INDEX idx_token ON token_records(token)")
        connection.execute(
            "CREATE TABLE metadata AS SELECT ?::VARCHAR AS source_path, ?::BIGINT AS row_count",
            [str(Path(source_path).resolve()), len(frame)],
        )
    finally:
        connection.close()

    os.replace(staging, database)
    return ImportResult(str(Path(source_path).resolve()), len(frame), skipped)


def get_token_ranking(
    database_path: str | os.PathLike[str],
    sort_by: str = "clicks",
    limit: int | None = 500,
    filters: Mapping[str, str] | None = None,
    ascending: bool = False,
    offset: int = 0,
    row_filters: Mapping[str, Mapping[str, object]] | None = None,
    sort_rules: Sequence[tuple[str, str]] | None = None,
) -> QueryResult:
    database = Path(database_path)
    if not database.exists():
        raise ValueError("请先导入Excel")
    if sort_by not in SORT_EXPRESSIONS:
        raise ValueError("不支持的排序维度")

    order_by_clause = _order_by_clause(sort_by, ascending, sort_rules)
    filter_clause, filter_parameters = _filter_clause(filters)
    metric_expressions = {
        "frequency": "count(*)",
        "impressions": "sum(records.impressions)",
        "clicks": "sum(records.clicks)",
        "orders": "sum(records.orders)",
        "ctr": "CASE WHEN sum(records.impressions) > 0 THEN sum(records.clicks) / sum(records.impressions) END",
        "cvr": "CASE WHEN sum(records.clicks) > 0 THEN sum(records.orders) / sum(records.clicks) END",
        "cost": "sum(records.cost)",
        "sales": "sum(records.sales)",
        "acos": "CASE WHEN sum(records.sales) > 0 THEN sum(records.cost) / sum(records.sales) END",
        "cpc": "CASE WHEN sum(records.clicks) > 0 THEN sum(records.cost) / sum(records.clicks) END",
    }
    summary_filter_clause, summary_filter_parameters = _summary_filter_clause(
        row_filters,
        "tokens.token",
        metric_expressions,
    )
    connection = duckdb.connect(str(database), read_only=True)
    try:
        totals = connection.execute(
            f"""
            SELECT
                count(*)::BIGINT,
                coalesce(sum(impressions), 0)::DOUBLE,
                coalesce(sum(clicks), 0)::DOUBLE,
                coalesce(sum(orders), 0)::DOUBLE,
                sum(cost)::DOUBLE,
                sum(sales)::DOUBLE
            FROM search_records AS records
            WHERE 1 = 1
            {filter_clause}
            """,
            filter_parameters,
        ).fetchone()
        total_items = int(connection.execute(
            f"""
            SELECT count(*) FROM (
                SELECT tokens.token
                FROM token_records AS tokens
                JOIN search_records AS records USING (record_id)
                WHERE 1 = 1
                  AND tokens.token NOT IN ({_EXCLUDED_WORDS_SQL})
                {filter_clause}
                GROUP BY tokens.token
                {summary_filter_clause}
            ) AS filtered_tokens
            """,
            [*filter_parameters, *summary_filter_parameters],
        ).fetchone()[0])
        limit_clause = "" if limit is None else "LIMIT ? OFFSET ?"
        query_parameters: list[object] = [*filter_parameters, *summary_filter_parameters]
        if limit is not None:
            query_parameters.extend([limit, max(0, offset)])
        ranking_rows = connection.execute(
            f"""
            WITH token_summary AS (
                SELECT
                    tokens.token AS search_term,
                    count(*)::BIGINT AS frequency,
                    sum(records.impressions)::DOUBLE AS impressions,
                    sum(records.clicks)::DOUBLE AS clicks,
                    sum(records.orders)::DOUBLE AS orders,
                    sum(records.cost)::DOUBLE AS cost,
                    sum(records.sales)::DOUBLE AS sales
                FROM token_records AS tokens
                JOIN search_records AS records USING (record_id)
                WHERE 1 = 1
                  AND tokens.token NOT IN ({_EXCLUDED_WORDS_SQL})
                {filter_clause}
                GROUP BY tokens.token
                {summary_filter_clause}
            )
            SELECT search_term, frequency, impressions, clicks, orders, cost, sales
            FROM token_summary
            ORDER BY {order_by_clause}
            {limit_clause}
            """,
            query_parameters,
        ).fetchall()
    finally:
        connection.close()

    frequency, impressions, clicks, orders, cost, sales = totals
    rows: list[dict[str, object]] = []
    for token, count, row_impressions, row_clicks, row_orders, row_cost, row_sales in ranking_rows:
        rows.append(
            {
                "search_term": token,
                "frequency": int(count),
                "impressions": int(round(row_impressions)),
                "clicks": int(round(row_clicks)),
                "orders": int(round(row_orders)),
                "ctr": row_clicks / row_impressions if row_impressions else None,
                "cvr": row_orders / row_clicks if row_clicks else None,
                "cost": float(row_cost) if row_cost is not None else None,
                "sales": float(row_sales) if row_sales is not None else None,
                "acos": row_cost / row_sales if row_sales else None,
                "cpc": row_cost / row_clicks if row_clicks and row_cost is not None else None,
            }
        )

    return QueryResult(
        query="",
        total_items=total_items,
        frequency=int(frequency),
        impressions=int(round(impressions)),
        clicks=int(round(clicks)),
        orders=int(round(orders)),
        ctr=clicks / impressions if impressions else None,
        cvr=orders / clicks if clicks else None,
        cost=float(cost) if cost is not None else None,
        sales=float(sales) if sales is not None else None,
        acos=cost / sales if sales else None,
        cpc=cost / clicks if clicks and cost is not None else None,
        rows=rows,
    )


def query_phrase(
    database_path: str | os.PathLike[str],
    phrase: str,
    sort_by: str = "clicks",
    limit: int | None = 100,
    filters: Mapping[str, str] | None = None,
    ascending: bool = False,
    _matching_terms: Iterable[str] | None = None,
    offset: int = 0,
    row_filters: Mapping[str, Mapping[str, object]] | None = None,
    sort_rules: Sequence[tuple[str, str]] | None = None,
) -> QueryResult:
    normalized = normalize_term(phrase)
    if not normalized:
        raise ValueError("请输入要查询的词元或连续词组")

    database = Path(database_path)
    if not database.exists():
        raise ValueError("请先导入Excel")
    if sort_by not in SORT_EXPRESSIONS:
        raise ValueError("不支持的排序维度")

    match_clause, match_parameters = _term_match_clause(
        "records",
        _matching_terms or (normalized,),
    )
    order_by_clause = _order_by_clause(sort_by, ascending, sort_rules)
    filter_clause, filter_parameters = _filter_clause(filters)
    metric_expressions = {
        "frequency": "count(*)",
        "impressions": "sum(records.impressions)",
        "clicks": "sum(records.clicks)",
        "orders": "sum(records.orders)",
        "ctr": "CASE WHEN sum(records.impressions) > 0 THEN sum(records.clicks) / sum(records.impressions) END",
        "cvr": "CASE WHEN sum(records.clicks) > 0 THEN sum(records.orders) / sum(records.clicks) END",
        "cost": "sum(records.cost)",
        "sales": "sum(records.sales)",
        "acos": "CASE WHEN sum(records.sales) > 0 THEN sum(records.cost) / sum(records.sales) END",
        "cpc": "CASE WHEN sum(records.clicks) > 0 THEN sum(records.cost) / sum(records.clicks) END",
    }
    summary_filter_clause, summary_filter_parameters = _summary_filter_clause(
        row_filters,
        "records.search_term",
        metric_expressions,
    )
    connection = duckdb.connect(str(database), read_only=True)
    try:
        totals = connection.execute(
            f"""
            SELECT
                count(*)::BIGINT AS frequency,
                count(DISTINCT search_term)::BIGINT AS total_items,
                coalesce(sum(impressions), 0)::DOUBLE AS impressions,
                coalesce(sum(clicks), 0)::DOUBLE AS clicks,
                coalesce(sum(orders), 0)::DOUBLE AS orders,
                sum(cost)::DOUBLE AS cost,
                sum(sales)::DOUBLE AS sales
            FROM search_records AS records
            WHERE {match_clause}
            {filter_clause}
            """,
            [*match_parameters, *filter_parameters],
        ).fetchone()
        total_items = int(connection.execute(
            f"""
            SELECT count(*) FROM (
                SELECT records.search_term
                FROM search_records AS records
                WHERE {match_clause}
                {filter_clause}
                GROUP BY records.search_term
                {summary_filter_clause}
            ) AS filtered_terms
            """,
            [*match_parameters, *filter_parameters, *summary_filter_parameters],
        ).fetchone()[0])
        limit_clause = "" if limit is None else "LIMIT ? OFFSET ?"
        detail_parameters: list[object] = [*match_parameters, *filter_parameters, *summary_filter_parameters]
        if limit is not None:
            detail_parameters.extend([limit, max(0, offset)])
        detail_rows = connection.execute(
            f"""
            WITH matched_summary AS (
                SELECT
                    search_term,
                    count(*)::BIGINT AS frequency,
                    sum(impressions)::DOUBLE AS impressions,
                    sum(clicks)::DOUBLE AS clicks,
                    sum(orders)::DOUBLE AS orders,
                    sum(cost)::DOUBLE AS cost,
                    sum(sales)::DOUBLE AS sales
                FROM search_records AS records
                WHERE {match_clause}
                {filter_clause}
                GROUP BY search_term
                {summary_filter_clause}
            )
            SELECT search_term, frequency, impressions, clicks, orders, cost, sales
            FROM matched_summary
            ORDER BY {order_by_clause}
            {limit_clause}
            """,
            detail_parameters,
        ).fetchall()
    finally:
        connection.close()

    frequency, _base_total_items, impressions, clicks, orders, cost, sales = totals
    rows: list[dict[str, object]] = []
    for term, count, row_impressions, row_clicks, row_orders, row_cost, row_sales in detail_rows:
        rows.append(
            {
                "search_term": term,
                "frequency": int(count),
                "impressions": int(round(row_impressions)),
                "clicks": int(round(row_clicks)),
                "orders": int(round(row_orders)),
                "ctr": row_clicks / row_impressions if row_impressions else None,
                "cvr": row_orders / row_clicks if row_clicks else None,
                "cost": float(row_cost) if row_cost is not None else None,
                "sales": float(row_sales) if row_sales is not None else None,
                "acos": row_cost / row_sales if row_sales else None,
                "cpc": row_cost / row_clicks if row_clicks and row_cost is not None else None,
            }
        )

    return QueryResult(
        query=normalized,
        total_items=int(total_items),
        frequency=int(frequency),
        impressions=int(round(impressions)),
        clicks=int(round(clicks)),
        orders=int(round(orders)),
        ctr=clicks / impressions if impressions else None,
        cvr=orders / clicks if clicks else None,
        cost=float(cost) if cost is not None else None,
        sales=float(sales) if sales is not None else None,
        acos=cost / sales if sales else None,
        cpc=cost / clicks if clicks and cost is not None else None,
        rows=rows,
    )


def query_token_drilldown(
    database_path: str | os.PathLike[str],
    token: str,
    sort_by: str = "clicks",
    limit: int | None = 100,
    filters: Mapping[str, str] | None = None,
    ascending: bool = False,
    offset: int = 0,
    row_filters: Mapping[str, Mapping[str, object]] | None = None,
    sort_rules: Sequence[tuple[str, str]] | None = None,
) -> QueryResult:
    normalized = normalize_term(token)
    if len(normalized.split()) != 1:
        raise ValueError("词元下钻仅支持单个词元")
    return query_phrase(
        database_path,
        normalized,
        sort_by=sort_by,
        limit=limit,
        filters=filters,
        ascending=ascending,
        _matching_terms=(normalized,),
        offset=offset,
        row_filters=row_filters,
        sort_rules=sort_rules,
    )


def query_campaign_drilldown(
    database_path: str | os.PathLike[str],
    search_term: str,
    sort_by: str = "clicks",
    limit: int | None = 100,
    filters: Mapping[str, str] | None = None,
    ascending: bool = False,
    offset: int = 0,
    row_filters: Mapping[str, Mapping[str, object]] | None = None,
    sort_rules: Sequence[tuple[str, str]] | None = None,
) -> QueryResult:
    normalized = normalize_term(search_term)
    if not normalized:
        raise ValueError("请选择要溯源的完整搜索词")
    database = Path(database_path)
    if not database.exists():
        raise ValueError("请先导入Excel")
    if sort_by not in SORT_EXPRESSIONS:
        raise ValueError("不支持的排序维度")

    order_by_clause = _order_by_clause(sort_by, ascending, sort_rules)
    filter_clause, filter_parameters = _filter_clause(filters)
    metric_expressions = {
        "frequency": "count(*)",
        "impressions": "sum(records.impressions)",
        "clicks": "sum(records.clicks)",
        "orders": "sum(records.orders)",
        "ctr": "CASE WHEN sum(records.impressions) > 0 THEN sum(records.clicks) / sum(records.impressions) END",
        "cvr": "CASE WHEN sum(records.clicks) > 0 THEN sum(records.orders) / sum(records.clicks) END",
        "cost": "sum(records.cost)",
        "sales": "sum(records.sales)",
        "acos": "CASE WHEN sum(records.sales) > 0 THEN sum(records.cost) / sum(records.sales) END",
        "cpc": "CASE WHEN sum(records.clicks) > 0 THEN sum(records.cost) / sum(records.clicks) END",
    }
    summary_filter_clause, summary_filter_parameters = _summary_filter_clause(
        row_filters,
        "records.campaign",
        metric_expressions,
    )
    connection = duckdb.connect(str(database), read_only=True)
    try:
        totals = connection.execute(
            f"""
            SELECT
                count(*)::BIGINT AS frequency,
                coalesce(sum(impressions), 0)::DOUBLE AS impressions,
                coalesce(sum(clicks), 0)::DOUBLE AS clicks,
                coalesce(sum(orders), 0)::DOUBLE AS orders,
                sum(cost)::DOUBLE AS cost,
                sum(sales)::DOUBLE AS sales
            FROM search_records AS records
            WHERE records.search_term = ?
              AND records.campaign <> ''
              {filter_clause}
            """,
            [normalized, *filter_parameters],
        ).fetchone()
        total_items = int(connection.execute(
            f"""
            SELECT count(*) FROM (
                SELECT records.campaign
                FROM search_records AS records
                WHERE records.search_term = ?
                  AND records.campaign <> ''
                  {filter_clause}
                GROUP BY records.campaign
                {summary_filter_clause}
            ) AS filtered_campaigns
            """,
            [normalized, *filter_parameters, *summary_filter_parameters],
        ).fetchone()[0])
        limit_clause = "" if limit is None else "LIMIT ? OFFSET ?"
        detail_parameters: list[object] = [normalized, *filter_parameters, *summary_filter_parameters]
        if limit is not None:
            detail_parameters.extend([limit, max(0, offset)])
        detail_rows = connection.execute(
            f"""
            WITH campaign_summary AS (
                SELECT
                    records.campaign AS search_term,
                    count(*)::BIGINT AS frequency,
                    sum(records.impressions)::DOUBLE AS impressions,
                    sum(records.clicks)::DOUBLE AS clicks,
                    sum(records.orders)::DOUBLE AS orders,
                    sum(records.cost)::DOUBLE AS cost,
                    sum(records.sales)::DOUBLE AS sales
                FROM search_records AS records
                WHERE records.search_term = ?
                  AND records.campaign <> ''
                  {filter_clause}
                GROUP BY records.campaign
                {summary_filter_clause}
            )
            SELECT search_term, frequency, impressions, clicks, orders, cost, sales
            FROM campaign_summary
            ORDER BY {order_by_clause}
            {limit_clause}
            """,
            detail_parameters,
        ).fetchall()
    finally:
        connection.close()

    frequency, impressions, clicks, orders, cost, sales = totals
    rows = [
        {
            "search_term": campaign,
            "frequency": int(count),
            "impressions": int(round(row_impressions)),
            "clicks": int(round(row_clicks)),
            "orders": int(round(row_orders)),
            "ctr": row_clicks / row_impressions if row_impressions else None,
            "cvr": row_orders / row_clicks if row_clicks else None,
            "cost": float(row_cost) if row_cost is not None else None,
            "sales": float(row_sales) if row_sales is not None else None,
            "acos": row_cost / row_sales if row_sales else None,
            "cpc": row_cost / row_clicks if row_clicks and row_cost is not None else None,
        }
        for campaign, count, row_impressions, row_clicks, row_orders, row_cost, row_sales in detail_rows
    ]
    return QueryResult(
        query=normalized,
        total_items=total_items,
        frequency=int(frequency),
        impressions=int(round(impressions)),
        clicks=int(round(clicks)),
        orders=int(round(orders)),
        ctr=clicks / impressions if impressions else None,
        cvr=orders / clicks if clicks else None,
        cost=float(cost) if cost is not None else None,
        sales=float(sales) if sales is not None else None,
        acos=cost / sales if sales else None,
        cpc=cost / clicks if clicks and cost is not None else None,
        rows=rows,
    )


def get_matching_campaigns(
    database_path: str | os.PathLike[str],
    token: str,
    filters: Mapping[str, str] | None = None,
) -> list[str]:
    normalized = normalize_term(token)
    if len(normalized.split()) != 1:
        raise ValueError("词元下钻仅支持单个词元")
    database = Path(database_path)
    if not database.exists():
        raise ValueError("请先导入Excel")

    match_clause, match_parameters = _term_match_clause(
        "records",
        (normalized,),
    )
    filter_clause, filter_parameters = _filter_clause(filters)
    connection = duckdb.connect(str(database), read_only=True)
    try:
        rows = connection.execute(
            f"""
            SELECT DISTINCT records.campaign
            FROM search_records AS records
            WHERE records.campaign <> ''
              AND {match_clause}
              {filter_clause}
            ORDER BY records.campaign
            """,
            [*match_parameters, *filter_parameters],
        ).fetchall()
    finally:
        connection.close()
    return [str(row[0]) for row in rows]
