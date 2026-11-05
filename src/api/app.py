"""FastAPI endpoints for the first Olist analytics dashboard."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.etl.olist import project_root

ROOT = project_root(Path(__file__).resolve())
PROCESSED = ROOT / "data" / "processed"
FRONTEND = ROOT / "frontend"

app = FastAPI(title="Olist Business Dashboard", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def load_dashboard_data() -> dict[str, pd.DataFrame]:
    required = ("sales", "orders", "reviews")
    missing = [name for name in required if not (PROCESSED / f"{name}.csv").exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing processed tables: {', '.join(missing)}. Run the cleaning notebook first."
        )
    sales = pd.read_csv(PROCESSED / "sales.csv", parse_dates=["order_date"])
    orders = pd.read_csv(PROCESSED / "orders.csv", parse_dates=["order_purchase_timestamp"])
    reviews = pd.read_csv(PROCESSED / "reviews.csv")
    return {"sales": sales, "orders": orders, "reviews": reviews}


def _money(value: float) -> float:
    return round(float(value), 2)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/dashboard")
def dashboard(
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    data = load_dashboard_data()
    sales = data["sales"].copy()
    sales["order_date"] = pd.to_datetime(sales["order_date"], errors="coerce")
    if start:
        sales = sales[sales["order_date"] >= pd.Timestamp(start)]
    if end:
        sales = sales[sales["order_date"] <= pd.Timestamp(end)]

    order_ids = sales["order_id"].dropna().unique()
    orders = data["orders"][data["orders"]["order_id"].isin(order_ids)].copy()
    reviews = data["reviews"][data["reviews"]["order_id"].isin(order_ids)].copy()
    order_revenue = sales.groupby("order_id", as_index=False)["revenue"].sum()
    monthly = (
        sales.assign(month=sales["order_date"].dt.to_period("M").astype(str))
        .groupby("month", as_index=False)
        .agg(revenue=("revenue", "sum"), orders=("order_id", "nunique"))
        .sort_values("month")
    )
    categories = (
        sales.groupby("product_category", dropna=False)
        .agg(revenue=("revenue", "sum"), items=("order_id", "size"))
        .reset_index()
        .sort_values("revenue", ascending=False)
        .head(8)
    )
    states = (
        sales.groupby("customer_state", dropna=False)
        .agg(revenue=("revenue", "sum"), orders=("order_id", "nunique"))
        .reset_index()
        .sort_values("revenue", ascending=False)
        .head(8)
    )
    delivered = orders["is_delivered"].astype("boolean") if "is_delivered" in orders else pd.Series(dtype="boolean")

    return {
        "period": {
            "from": sales["order_date"].min().strftime("%Y-%m-%d") if not sales.empty else None,
            "to": sales["order_date"].max().strftime("%Y-%m-%d") if not sales.empty else None,
        },
        "kpis": {
            "revenue": _money(sales["revenue"].sum()),
            "orders": int(sales["order_id"].nunique()),
            "items": int(len(sales)),
            "average_order_value": _money(order_revenue["revenue"].mean()) if not order_revenue.empty else 0,
            "delivery_rate": round(float(delivered.mean() * 100), 1) if not delivered.empty else 0,
            "average_review": round(float(pd.to_numeric(reviews["review_score"], errors="coerce").mean()), 2)
            if not reviews.empty
            else 0,
        },
        "monthly": [
            {"month": row.month, "revenue": _money(row.revenue), "orders": int(row.orders)}
            for row in monthly.itertuples(index=False)
        ],
        "categories": [
            {"name": str(row.product_category or "unknown"), "revenue": _money(row.revenue), "items": int(row.items)}
            for row in categories.itertuples(index=False)
        ],
        "states": [
            {"name": str(row.customer_state or "unknown"), "revenue": _money(row.revenue), "orders": int(row.orders)}
            for row in states.itertuples(index=False)
        ],
        "data_note": "Revenue is based on item prices. Olist does not include purchase cost or stock snapshots.",
    }


if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
