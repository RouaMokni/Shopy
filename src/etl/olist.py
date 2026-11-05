"""Read, clean, and prepare the Olist tables used by the dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pandas as pd

TABLE_FILES: Final = {
    "customers": "olist_customers_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}

ZIP_COLUMNS: Final = {
    "customer_zip_code_prefix",
    "seller_zip_code_prefix",
    "geolocation_zip_code_prefix",
}

ORDER_DATE_COLUMNS: Final = (
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
)

EXCLUDED_STATUSES: Final = {"canceled", "unavailable"}


def project_root(start: Path | None = None) -> Path:
    """Find the project directory without depending on the notebook cwd."""
    current = (start or Path.cwd()).resolve()
    for path in (current, *current.parents):
        if (path / "requirements.txt").exists() and (path / "data").is_dir():
            return path
    raise FileNotFoundError("Could not find the project root.")


def read_olist_tables(raw_dir: Path) -> dict[str, pd.DataFrame]:
    """Load every known Olist CSV, preserving postal-code leading zeroes."""
    tables: dict[str, pd.DataFrame] = {}
    for name, filename in TABLE_FILES.items():
        path = raw_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing Olist file: {path}")
        header = pd.read_csv(path, nrows=0).columns
        dtype = {column: "string" for column in header if column in ZIP_COLUMNS}
        tables[name] = pd.read_csv(path, dtype=dtype)
    return tables


def _strip_text(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for column in columns:
        if column in df:
            df[column] = df[column].astype("string").str.strip()
    return df


def clean_olist_tables(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Apply dataset-specific cleaning rules and return independent copies."""
    clean = {name: table.copy() for name, table in raw.items()}

    customers = _strip_text(clean["customers"], ["customer_city", "customer_state"])
    customers["customer_city"] = customers["customer_city"].str.lower()
    customers["customer_state"] = customers["customer_state"].str.upper()
    clean["customers"] = customers.drop_duplicates("customer_id").reset_index(drop=True)

    orders = _strip_text(clean["orders"], ["order_status"])
    orders = orders.drop_duplicates("order_id").reset_index(drop=True)
    for column in ORDER_DATE_COLUMNS:
        orders[column] = pd.to_datetime(orders[column], errors="coerce")
    orders["is_delivered"] = orders["order_delivered_customer_date"].notna()
    orders["delivery_days"] = (
        orders["order_delivered_customer_date"] - orders["order_purchase_timestamp"]
    ).dt.total_seconds().div(86400).round(2)
    orders.loc[orders["delivery_days"] < 0, "delivery_days"] = pd.NA
    clean["orders"] = orders

    products = clean["products"].drop_duplicates("product_id").reset_index(drop=True)
    translations = clean["category_translation"].drop_duplicates("product_category_name")
    products = products.merge(translations, on="product_category_name", how="left")
    products["product_category"] = (
        products["product_category_name_english"]
        .fillna(products["product_category_name"])
        .fillna("unknown")
        .astype("string")
        .str.strip()
        .str.lower()
    )
    clean["products"] = products.drop(columns=["product_category_name_english"])

    items = clean["items"].drop_duplicates(["order_id", "order_item_id"])
    items["shipping_limit_date"] = pd.to_datetime(items["shipping_limit_date"], errors="coerce")
    items["price"] = pd.to_numeric(items["price"], errors="coerce")
    items["freight_value"] = pd.to_numeric(items["freight_value"], errors="coerce")
    items = items[
        items["order_id"].isin(clean["orders"]["order_id"])
        & items["product_id"].isin(clean["products"]["product_id"])
        & items["price"].gt(0)
    ]
    clean["items"] = items.reset_index(drop=True)

    payments = clean["payments"].drop_duplicates(["order_id", "payment_sequential"])
    payments["payment_value"] = pd.to_numeric(payments["payment_value"], errors="coerce")
    clean["payments"] = payments.reset_index(drop=True)

    reviews = clean["reviews"].drop_duplicates(["review_id", "order_id"])
    for column in ("review_creation_date", "review_answer_timestamp"):
        reviews[column] = pd.to_datetime(reviews[column], errors="coerce")
    reviews = reviews.sort_values("review_answer_timestamp").drop_duplicates("order_id", keep="last")
    clean["reviews"] = reviews.reset_index(drop=True)

    clean["sellers"] = clean["sellers"].drop_duplicates("seller_id").reset_index(drop=True)
    clean["geolocation"] = clean["geolocation"].drop_duplicates().reset_index(drop=True)
    return clean


def build_sales_table(clean: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Create one row per item sold, enriched with order and customer context."""
    valid_orders = clean["orders"].loc[
        ~clean["orders"]["order_status"].isin(EXCLUDED_STATUSES),
        ["order_id", "customer_id", "order_status", "order_purchase_timestamp"],
    ]
    sales = clean["items"].merge(valid_orders, on="order_id", how="inner")
    sales = sales.merge(
        clean["products"][["product_id", "product_category"]],
        on="product_id",
        how="left",
    )
    sales = sales.merge(
        clean["customers"][["customer_id", "customer_state"]],
        on="customer_id",
        how="left",
    )
    sales["order_date"] = sales["order_purchase_timestamp"].dt.normalize()
    sales["revenue"] = sales["price"].round(2)
    sales["total_with_freight"] = (sales["price"] + sales["freight_value"]).round(2)
    return sales.reset_index(drop=True)


def prepare_olist_data(
    raw_dir: Path,
    processed_dir: Path | None = None,
) -> dict[str, pd.DataFrame]:
    """Read, clean, build sales, and optionally write the processed tables."""
    clean = clean_olist_tables(read_olist_tables(raw_dir))
    clean["sales"] = build_sales_table(clean)
    if processed_dir is not None:
        processed_dir.mkdir(parents=True, exist_ok=True)
        for name, table in clean.items():
            table.to_csv(processed_dir / f"{name}.csv", index=False)
    return clean
