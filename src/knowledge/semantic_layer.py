"""The semantic layer: metric questions answered from metrics.yaml.

metrics.yaml says what each metric means. This module reads it, checks it,
and builds the SQL for a metric from a fixed template. Nothing the caller
passes is ever written into the SQL: metric and dimension names are looked
up in the definitions, and filter values are bound as parameters.

Two templates, by the grain of the metric:

- item:  one row per order item. Joins to products and sellers are
         many-to-one, so nothing is counted twice.
- order: one row per order. When a dimension lives on the items (category,
         seller state) an order can fall into several groups, so the query
         first takes the DISTINCT (order, dimension) pairs and then counts.
"""

import sqlite3
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

import config
from src import messages

METRICS_PATH = Path(__file__).resolve().parent.parent.parent / "metrics.yaml"

MAX_ROWS = 1000
MAX_GROUP_BY = 2

GRAINS = ("order", "item")
LEVELS = ("order", "item")
PERIOD_FILTERS = ("purchase_from", "purchase_to")

# Joins a dimension needs, by the alias its expression uses.
ORDER_LEVEL_JOINS = "JOIN customers AS c ON c.customer_id = o.customer_id"
ITEM_LEVEL_JOINS = (
    "LEFT JOIN products AS p ON p.product_id = i.product_id "
    "LEFT JOIN product_category_name_translation AS t "
    "ON t.product_category_name = p.product_category_name "
    "JOIN sellers AS s ON s.seller_id = i.seller_id"
)

# Per-order sources a metric may ask for with "join". Each has one row per
# order, so joining it never multiplies orders.
METRIC_JOINS = {
    "order_totals": (
        "LEFT JOIN (SELECT order_id, SUM(price) AS price_total "
        "FROM order_items GROUP BY order_id) AS ot ON ot.order_id = o.order_id"
    ),
    "order_reviews": (
        "JOIN (SELECT order_id, AVG(review_score) AS review_score "
        "FROM order_reviews "
        "WHERE DATE(review_creation_date) <= DATE(:simulated_today) "
        "GROUP BY order_id) AS r ON r.order_id = o.order_id"
    ),
}

# Every metric counts only orders that exist on the simulated today.
PURCHASED_BY_TODAY = "DATE(o.order_purchase_timestamp) <= DATE(:simulated_today)"


@dataclass(frozen=True)
class Dimension:
    name: str
    description: str
    level: str
    expression: str


@dataclass(frozen=True)
class Metric:
    name: str
    description: str
    grain: str
    base_filter: str
    numerator: str
    denominator: str | None
    dimensions: tuple[str, ...]
    caveat: str
    join: str | None = None


@dataclass(frozen=True)
class SemanticLayer:
    dimensions: dict[str, Dimension]
    metrics: dict[str, Metric]


def parse_semantic_layer(text: str) -> SemanticLayer:
    """Read and check the definitions; raise ValueError on the first fault."""
    data = yaml.safe_load(text)

    dimensions = {}
    for name, fields in data["dimensions"].items():
        if not name.isidentifier():
            raise ValueError(f"dimension {name!r}: the name must be an identifier")
        try:
            dimension = Dimension(name=name, **fields)
        except TypeError as error:
            raise ValueError(f"dimension {name!r}: {error}") from error
        if dimension.level not in LEVELS:
            raise ValueError(f"dimension {name!r}: unknown level {dimension.level!r}")
        dimensions[name] = dimension

    metrics = {}
    for name, fields in data["metrics"].items():
        try:
            metric = Metric(
                name=name, **{**fields, "dimensions": tuple(fields["dimensions"])}
            )
        except (KeyError, TypeError) as error:
            raise ValueError(f"metric {name!r}: {error}") from error
        if metric.grain not in GRAINS:
            raise ValueError(f"metric {name!r}: unknown grain {metric.grain!r}")
        if metric.join is not None and metric.join not in METRIC_JOINS:
            raise ValueError(f"metric {name!r}: unknown join {metric.join!r}")
        for dimension_name in metric.dimensions:
            if dimension_name not in dimensions:
                raise ValueError(
                    f"metric {name!r}: unknown dimension {dimension_name!r}"
                )
        if not metric.caveat.strip():
            raise ValueError(f"metric {name!r}: the caveat is empty")
        metrics[name] = metric

    return SemanticLayer(dimensions, metrics)


@lru_cache(maxsize=1)
def load_semantic_layer() -> SemanticLayer:
    """The definitions in metrics.yaml, read once."""
    return parse_semantic_layer(METRICS_PATH.read_text(encoding="utf-8"))


def list_metrics() -> dict:
    """List the metrics that can be computed, with what each one means.

    Look here first for any question about numbers. Each metric comes with
    its description, the dimensions it can be grouped or filtered by, and a
    caveat that must be repeated whenever the metric is reported.
    """
    layer = load_semantic_layer()
    return {
        "metrics": [
            {
                "name": metric.name,
                "description": metric.description,
                "dimensions": list(metric.dimensions),
                "caveat": metric.caveat,
            }
            for metric in layer.metrics.values()
        ],
        "dimensions": {
            dimension.name: dimension.description
            for dimension in layer.dimensions.values()
        },
        "period_filters": list(PERIOD_FILTERS),
    }


def error(code: str, message: str) -> dict:
    return {"error": code, "message": message}


def build_filters(
    metric: Metric, layer: SemanticLayer, filters: dict
) -> tuple[list[str], dict[str, str]] | dict:
    """Turn the filters into SQL conditions and the values bound to them.

    Returns an error answer instead when a filter is not allowed.
    """
    conditions: list[str] = []
    params: dict[str, str] = {}
    for key, value in filters.items():
        if key in PERIOD_FILTERS:
            try:
                date.fromisoformat(value)
            except (TypeError, ValueError):
                return error(
                    "INVALID_FILTER", messages.INVALID_PERIOD_FILTER.format(name=key)
                )
            operator = ">=" if key == "purchase_from" else "<="
            conditions.append(
                f"DATE(o.order_purchase_timestamp) {operator} DATE(:{key})"
            )
            params[key] = value
            continue

        if key not in metric.dimensions:
            return error(
                "INVALID_FILTER",
                messages.INVALID_METRIC_FILTER.format(
                    name=key,
                    allowed=", ".join((*metric.dimensions, *PERIOD_FILTERS)),
                ),
            )
        values = value if isinstance(value, list) else [value]
        if not values or not all(isinstance(item, str) for item in values):
            return error(
                "INVALID_FILTER", messages.INVALID_FILTER_VALUE.format(name=key)
            )
        names = [f"{key}_{position}" for position in range(len(values))]
        placeholders = ", ".join(f":{name}" for name in names)
        conditions.append(f"{layer.dimensions[key].expression} IN ({placeholders})")
        params.update(zip(names, values, strict=True))
    return conditions, params


def build_sql(
    metric: Metric,
    layer: SemanticLayer,
    group_by: list[str],
    filter_conditions: list[str],
    filtered: list[str],
) -> str:
    """Build the SQL of a metric from its template."""
    select_dimensions = [
        f"{layer.dimensions[name].expression} AS {name}" for name in group_by
    ]
    used_levels = {layer.dimensions[name].level for name in (*group_by, *filtered)}

    # A metric without a denominator is a plain total; otherwise a ratio.
    aggregates = [f"{metric.numerator} AS numerator"]
    result_columns = [*group_by, "numerator"]
    value = "numerator"
    if metric.denominator is not None:
        aggregates.append(f"{metric.denominator} AS denominator")
        result_columns.append("denominator")
        value = "1.0 * numerator / NULLIF(denominator, 0)"
    grouping = f" GROUP BY {', '.join(group_by)}" if group_by else ""
    ordering = f" ORDER BY {', '.join(group_by)}" if group_by else ""

    if metric.grain == "item":
        conditions = [PURCHASED_BY_TODAY, f"({metric.base_filter})", *filter_conditions]
        inner = (
            f"SELECT {', '.join((*select_dimensions, *aggregates))} "
            "FROM order_items AS i "
            "JOIN orders AS o ON o.order_id = i.order_id "
            f"{ORDER_LEVEL_JOINS} {ITEM_LEVEL_JOINS} "
            f"WHERE {' AND '.join(conditions)}"
            f"{grouping}"
        )
    else:
        # Step 1: the orders in scope, once per value of the dimensions.
        scope_joins = ORDER_LEVEL_JOINS
        if "item" in used_levels:
            scope_joins += (
                f" JOIN order_items AS i ON i.order_id = o.order_id {ITEM_LEVEL_JOINS}"
            )
        scope_conditions = [PURCHASED_BY_TODAY, *filter_conditions]
        scope = (
            f"SELECT DISTINCT {', '.join(('o.order_id', *select_dimensions))} "
            f"FROM orders AS o {scope_joins} "
            f"WHERE {' AND '.join(scope_conditions)}"
        )
        # Step 2: the metric over those orders.
        inner = (
            f"SELECT {', '.join((*group_by, *aggregates))} "
            f"FROM ({scope}) AS scope "
            "JOIN orders AS o ON o.order_id = scope.order_id "
            f"{METRIC_JOINS[metric.join] if metric.join else ''} "
            f"WHERE ({metric.base_filter})"
            f"{grouping}"
        )

    return (
        f"SELECT {', '.join(result_columns)}, {value} AS value "
        f"FROM ({inner}) AS result{ordering} LIMIT {MAX_ROWS}"
    )


def run_metric(
    conn: sqlite3.Connection,
    metric_name: str,
    filters: dict | None = None,
    group_by: list[str] | None = None,
    today: date = config.SIMULATED_TODAY,
) -> dict:
    """Compute one metric from its definition and return the result table.

    metric_name is a name from list_metrics. group_by is a list of at most
    two of the metric's dimensions. filters maps a dimension to one value or
    a list of values (for example {"customer_state": ["SP", "RJ"]}); the
    keys purchase_from and purchase_to (YYYY-MM-DD) limit the purchase day.

    The result holds the columns, the rows (at most 1000), the SQL that was
    run and the metric's caveat. Always repeat the caveat when reporting the
    number, and never present the result as a cause of anything.
    """
    layer = load_semantic_layer()
    filters = filters or {}
    group_by = group_by or []

    metric = layer.metrics.get(metric_name)
    if metric is None:
        return error(
            "UNKNOWN_METRIC",
            messages.UNKNOWN_METRIC.format(allowed=", ".join(layer.metrics)),
        )

    not_allowed = [name for name in group_by if name not in metric.dimensions]
    if not_allowed:
        return error(
            "INVALID_DIMENSION",
            messages.INVALID_DIMENSION.format(
                name=", ".join(map(str, not_allowed)),
                allowed=", ".join(metric.dimensions),
            ),
        )
    if len(group_by) != len(set(group_by)) or len(group_by) > MAX_GROUP_BY:
        return error(
            "INVALID_DIMENSION",
            messages.TOO_MANY_DIMENSIONS.format(limit=MAX_GROUP_BY),
        )
    item_level = [name for name in group_by if layer.dimensions[name].level == "item"]
    if metric.grain == "order" and len(item_level) > 1:
        # An order would be counted once per combination of the two.
        return error(
            "INVALID_DIMENSION",
            messages.ITEM_DIMENSIONS_TOGETHER.format(names=", ".join(item_level)),
        )

    built = build_filters(metric, layer, filters)
    if isinstance(built, dict):
        return built
    filter_conditions, params = built
    filtered = [name for name in filters if name not in PERIOD_FILTERS]

    sql = build_sql(metric, layer, group_by, filter_conditions, filtered)
    params["simulated_today"] = today.isoformat()
    cursor = conn.execute(sql, params)
    columns = [column[0] for column in cursor.description]
    rows = [list(row) for row in cursor.fetchall()]

    return {
        "metric": metric.name,
        "description": metric.description,
        "caveat": metric.caveat,
        "columns": columns,
        "rows": rows,
        "sql": sql,
        "params": params,
    }
