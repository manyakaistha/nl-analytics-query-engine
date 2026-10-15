"""One bounded DuckDB executor; trusted loading is separate from untrusted SQL."""

from __future__ import annotations
import json
import threading
import time
import duckdb
import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope
from app.config import (
    RAW_DATA_DIR,
    MAX_RESULT_ROWS,
    MAX_RESULT_BYTES,
    SQL_TIMEOUT_SECONDS,
    DUCKDB_MEMORY_MB,
)
from scripts.validate_data import validate_data

_connection = None
_data_version = None
_profile = None
_lock = threading.RLock()
TABLES = {"sales_data", "targets", "sales_with_revenue"}
FUNCTIONS = set(
    "AND OR SUM COUNT AVG MIN MAX COALESCE NULLIF ROUND ABS FLOOR CEIL CEILING UPPER LOWER TRIM LENGTH SUBSTRING REPLACE CONCAT CONCAT_WS CAST TRY_CAST EXTRACT STRFTIME DATE_TRUNC DATE_PART DATE_DIFF DATEDIFF DATE_ADD LAST_DAY DAY MONTH YEAR RANK DENSE_RANK ROW_NUMBER LAG LEAD FIRST_VALUE LAST_VALUE NTILE PERCENT_RANK CUME_DIST STRING_AGG GROUP_CONCAT GREATEST LEAST IF CASE TIME_TO_STR TS_OR_DS_TO_DATE CURRENT_DATE".split()
)


def get_connection():
    global _connection
    with _lock:
        if _connection is None:
            _connection = _init_database()
        return _connection


def _init_database():
    global _data_version, _profile
    _profile = validate_data()
    con = duckdb.connect(
        ":memory:",
        config={
            "threads": 1,
            "memory_limit": f"{DUCKDB_MEMORY_MB}MB",
            "max_temp_directory_size": "0B",
        },
    )
    # Explicit decimal types keep monetary calculations reproducible.
    con.execute(
        "CREATE TABLE sales_data AS SELECT * FROM read_csv(?, header=true, types={'order_date':'DATE','quantity':'INTEGER','unit_price':'DECIMAL(14,2)','discount':'DECIMAL(5,4)','shipping_cost':'DECIMAL(14,2)','profit':'DECIMAL(14,2)'})",
        [str(RAW_DATA_DIR / "sales_data.csv")],
    )
    con.execute(
        "CREATE TABLE targets AS SELECT * FROM read_csv(?, header=true, types={'month':'VARCHAR','target_revenue':'DECIMAL(16,2)'})",
        [str(RAW_DATA_DIR / "targets.csv")],
    )
    con.execute(
        "CREATE VIEW sales_with_revenue AS SELECT *, quantity * unit_price * (1-discount) AS revenue, strftime(order_date, '%Y-%m') AS order_month FROM sales_data"
    )
    con.execute("SET enable_external_access=false")
    con.execute("SET lock_configuration=true")
    _data_version = _profile["dataset_version"]
    return con


def get_data_version():
    get_connection()
    return _data_version


def get_profile():
    get_connection()
    return dict(_profile)


def close_database():
    global _connection
    with _lock:
        if _connection is not None:
            _connection.close()
            _connection = None


def validate_sql(sql: str) -> str:
    if len(sql) > 12000:
        raise PermissionError("SQL is too long")
    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except sqlglot.errors.ParseError:
        raise PermissionError("Invalid SQL syntax") from None
    if len(statements) != 1 or not isinstance(
        statements[0], (exp.Select, exp.Union, exp.Intersect, exp.Except)
    ):
        raise PermissionError("Read-only violation: only a single SELECT is allowed")
    tree = statements[0]
    forbidden = (
        exp.Command,
        exp.DDL,
        exp.DML,
        exp.Into,
        exp.Lock,
        exp.Parameter,
        exp.Placeholder,
    )
    for node in tree.walk():
        if isinstance(node, forbidden) or (
            isinstance(node, exp.With) and node.args.get("recursive")
        ):
            raise PermissionError("Unsupported SQL operation")
        if isinstance(node, exp.Func):
            name = (
                node.name.upper()
                if isinstance(node, exp.Anonymous)
                else node.sql_name()
            )
            if name not in FUNCTIONS:
                raise PermissionError("Unsupported SQL function")
        if isinstance(node, exp.Table):
            if not isinstance(node.this, exp.Identifier) or node.db or node.catalog:
                raise PermissionError(
                    "External tables and table functions are disabled"
                )
    for scope in traverse_scope(tree):
        for source in scope.sources.values():
            if isinstance(source, exp.Table) and source.name.lower() not in TABLES:
                raise PermissionError("Query references an unapproved table")
    return tree.sql(dialect="duckdb").rstrip(";")


def execute_sql(sql: str, timings: dict | None = None) -> tuple[list[dict], list[str]]:
    validation_start = time.perf_counter()
    safe_sql = validate_sql(sql)
    if timings is not None:
        timings["sql_validation"] = timings.get("sql_validation", 0) + round(
            (time.perf_counter() - validation_start) * 1000, 3
        )
    with _lock:
        execution_start = time.perf_counter()
        con = get_connection()
        # Only this query owns the connection until its timer is cancelled AND joined.
        timer = threading.Timer(SQL_TIMEOUT_SECONDS, con.interrupt)
        timer.daemon = True
        timer.start()
        try:
            result = con.execute(
                f"SELECT * FROM ({safe_sql}) AS bounded_result LIMIT {MAX_RESULT_ROWS + 1}"
            )
            columns = [d[0] for d in result.description]
            if len(columns) > 40:
                raise PermissionError("Too many result columns")
            raw = result.fetchmany(MAX_RESULT_ROWS + 1)
            if len(raw) > MAX_RESULT_ROWS:
                raise PermissionError(
                    f"Result exceeds {MAX_RESULT_ROWS} rows; use a filter or LIMIT"
                )
            rows = [dict(zip(columns, row)) for row in raw]
            if len(json.dumps(rows, default=str).encode()) > MAX_RESULT_BYTES:
                raise PermissionError(
                    "Result is too large; select fewer columns or rows"
                )
            return rows, columns
        finally:
            timer.cancel()
            timer.join()
            if timings is not None:
                timings["duckdb_execution"] = timings.get(
                    "duckdb_execution", 0
                ) + round((time.perf_counter() - execution_start) * 1000, 3)
