"""Strict validation of the bundled, unmodified synthetic order lines."""

import csv
import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "data"
SALES_COLUMNS = "order_id order_date region country city customer_id customer_segment product_category product_subcategory product_name quantity unit_price discount shipping_cost profit".split()
TARGET_COLUMNS = ["region", "month", "target_revenue"]


def validate_data(root: Path = ROOT) -> dict:
    digest = hashlib.sha256()
    orders, customers, dates, monthly = {}, {}, [], {}
    revenue, profit = Decimal(0), Decimal(0)
    count = 0
    categories = {
        name: set()
        for name in [
            "region",
            "country",
            "city",
            "customer_segment",
            "product_category",
            "product_subcategory",
            "product_name",
        ]
    }
    geography, cities, subcategories, products = {}, {}, {}, {}
    for name, columns in [
        ("sales_data.csv", SALES_COLUMNS),
        ("targets.csv", TARGET_COLUMNS),
    ]:
        path = root / name
        digest.update(name.encode())
        digest.update(path.read_bytes())
        with path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames != columns:
                raise ValueError(f"{name}: unexpected schema")
            target_keys = set()
            for row in reader:
                if set(row) != set(columns) or any(
                    v is None or not v.strip() for v in row.values()
                ):
                    raise ValueError(f"{name}: null or malformed row")
                if name == "targets.csv":
                    key = (row["region"], row["month"])
                    if key in target_keys or row["region"] not in {
                        "APAC",
                        "EMEA",
                        "NA",
                    }:
                        raise ValueError("Invalid or duplicate target dimension")
                    if (
                        row["month"] not in {"2024-01", "2024-02", "2024-03"}
                        or Decimal(row["target_revenue"]) <= 0
                    ):
                        raise ValueError("Invalid target period/value")
                    target_keys.add(key)
                    continue
                count += 1
                if (
                    int(row["order_id"]) <= 0
                    or row["region"] not in {"APAC", "EMEA", "NA"}
                    or row["customer_segment"]
                    not in {"Consumer", "Corporate", "Home Office"}
                ):
                    raise ValueError("Invalid identifier or categorical dimension")
                for column in categories:
                    categories[column].add(row[column])
                for mapping, key, value in [
                    (geography, row["country"], row["region"]),
                    (cities, row["city"], row["country"]),
                    (
                        subcategories,
                        row["product_subcategory"],
                        row["product_category"],
                    ),
                    (products, row["product_name"], row["product_subcategory"]),
                ]:
                    if mapping.setdefault(key, value) != value:
                        raise ValueError("Inconsistent geography or product hierarchy")
                day = date.fromisoformat(row["order_date"])
                if not date(2024, 1, 1) <= day <= date(2024, 3, 31):
                    raise ValueError("Sales date outside dataset scope")
                dates.append(day)
                values = {
                    c: Decimal(row[c])
                    for c in [
                        "quantity",
                        "unit_price",
                        "discount",
                        "shipping_cost",
                        "profit",
                    ]
                }
                if not all(v.is_finite() for v in values.values()):
                    raise ValueError("Non-finite number")
                if (
                    values["quantity"] <= 0
                    or values["quantity"] != values["quantity"].to_integral_value()
                    or values["unit_price"] < 0
                    or values["shipping_cost"] < 0
                    or not 0 <= values["discount"] <= 1
                ):
                    raise ValueError("Invalid numeric value")
                order = tuple(
                    row[c]
                    for c in [
                        "order_date",
                        "customer_id",
                        "region",
                        "country",
                        "city",
                        "customer_segment",
                    ]
                )
                customer = tuple(
                    row[c] for c in ["region", "country", "city", "customer_segment"]
                )
                if (
                    orders.setdefault(row["order_id"], order) != order
                    or customers.setdefault(row["customer_id"], customer) != customer
                ):
                    raise ValueError("Inconsistent order/customer dimensions")
                line_revenue = (
                    values["quantity"] * values["unit_price"] * (1 - values["discount"])
                )
                revenue += line_revenue
                profit += values["profit"]
                key = (row["region"], row["order_date"][:7])
                monthly[key] = monthly.get(key, Decimal(0)) + line_revenue
    if set(monthly) != target_keys:
        raise ValueError("Sales and target dimensions differ")
    return dict(
        rows=count,
        columns=SALES_COLUMNS,
        distinct_orders=len(orders),
        distinct_customers=len(customers),
        date_range=[str(min(dates)), str(max(dates))],
        target_rows=len(target_keys),
        categorical_dimensions={
            key: sorted(values) for key, values in categories.items()
        },
        total_revenue=str(revenue),
        total_profit=str(profit),
        dataset_version=digest.hexdigest(),
        monthly_revenue={"/".join(k): str(v) for k, v in sorted(monthly.items())},
    )


if __name__ == "__main__":
    print(json.dumps(validate_data(), indent=2))
