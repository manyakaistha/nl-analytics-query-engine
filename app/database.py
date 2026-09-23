"""
DuckDB connection manager — loads processed CSVs into in-memory tables.
"""

from __future__ import annotations

import hashlib

import duckdb

from app.config import DATA_DIR


# Module-level connection (singleton per process)
_connection: duckdb.DuckDBPyConnection | None = None
_data_version: str | None = None


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return the shared in-memory DuckDB connection, initializing on first call."""
    global _connection
    if _connection is None:
        _connection = _init_database()
    return _connection


def get_data_version() -> str:
    """Identify the CSV snapshot loaded into the current in-memory database."""
    get_connection()
    assert _data_version is not None
    return _data_version


def _init_database() -> duckdb.DuckDBPyConnection:
    """
    Create an in-memory DuckDB connection and load the processed CSV files
    as permanent tables.
    """
    global _data_version
    con = duckdb.connect(database=":memory:")

    sales_path = DATA_DIR / "sales_data.csv"
    targets_path = DATA_DIR / "targets.csv"
    digest = hashlib.sha256()
    for path in (sales_path, targets_path):
        digest.update(path.name.encode("utf-8"))
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)

    con.execute(f"""
        CREATE TABLE sales_data AS
        SELECT * FROM read_csv_auto('{sales_path}', header=true)
    """)

    con.execute(f"""
        CREATE TABLE targets AS
        SELECT * FROM read_csv_auto('{targets_path}', header=true)
    """)

    # Create a convenience view with the revenue metric pre-computed
    con.execute("""
        CREATE VIEW sales_with_revenue AS
        SELECT
            *,
            quantity * unit_price * (1 - discount) AS revenue,
            STRFTIME(order_date, '%Y-%m') AS order_month
        FROM sales_data
    """)

    _verify_tables(con)
    # The statement-type check below does not stop SELECT * FROM read_csv_auto(...)
    # or similar table functions from reading arbitrary local files. Loading is
    # complete, so prevent query-time access to files and remote resources.
    con.execute("SET enable_external_access = false")
    _data_version = digest.hexdigest()
    return con


def _verify_tables(con: duckdb.DuckDBPyConnection) -> None:
    """Print table info at startup for debugging."""
    for table in ["sales_data", "targets", "sales_with_revenue"]:
        try:
            count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            cols = [
                row[0]
                for row in con.execute(f"DESCRIBE {table}").fetchall()
            ]
            print(f"  ✓ {table}: {count} rows, columns={cols}")
        except Exception as exc:
            print(f"  ✗ {table}: {exc}")


def execute_sql(sql: str) -> tuple[list[dict], list[str]]:
    """
    Execute a SQL query against DuckDB and return (rows_as_dicts, column_names).
    Raises duckdb.Error on invalid SQL, and PermissionError on anything other
    than a single read-only SELECT statement.
    """
    con = get_connection()

    # Read-only guard: the prompt forbids writes, but never trust the model alone
    statements = con.extract_statements(sql)
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
        kinds = ", ".join(s.type.name for s in statements) or "none"
        raise PermissionError(
            f"Read-only violation: only a single SELECT statement is allowed (got: {kinds})."
        )

    result = con.execute(sql)
    columns = [desc[0] for desc in result.description]
    rows = [dict(zip(columns, row)) for row in result.fetchall()]
    return rows, columns
