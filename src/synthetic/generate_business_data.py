"""Générateur de données business SYNTHÉTIQUES pour ShopPulse AI.

Olist ne contient ni coût d'achat, ni stock, ni délai fournisseur. Ce script
fabrique ces informations de façon reproductible (seed fixe) pour pouvoir
développer et tester la plateforme.

IMPORTANT : toutes les valeurs produites ici sont INVENTÉES. Elles servent à
tester le code, pas à valider des recommandations commerciales. Chaque ligne
porte `is_synthetic = True`.

Usage :
    # Démo sans Olist
    python -m shoppulse.synthetic.generate_business_data --n-products 200

    # Avec Olist (dossier contenant olist_order_items_dataset.csv)
    python -m shoppulse.synthetic.generate_business_data --olist-dir data/raw/olist
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from ..etl.validate import ensure_valid_product_business_data

# Hypothèses arbitraires (à documenter dans le rapport / README)
PROFILES = ("healthy", "overstock", "low_stock")
PROFILE_PROBS = (0.80, 0.12, 0.08)
OLIST_HISTORY_DAYS = 700  # ~ sept. 2016 -> août 2018
DEFAULT_SNAPSHOT_DATE = "2018-08-29"


def load_olist_products(olist_dir: str | Path) -> pd.DataFrame:
    """Prix médian et nombre de lignes vendues par produit, depuis Olist."""
    path = Path(olist_dir) / "olist_order_items_dataset.csv"
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")
    items = pd.read_csv(path, usecols=["product_id", "price"])
    products = (
        items.groupby("product_id")
        .agg(unit_price=("price", "median"), n_sold=("price", "size"))
        .reset_index()
    )
    return products[products["unit_price"] > 0].reset_index(drop=True)


def make_demo_products(n_products: int, seed: int) -> pd.DataFrame:
    """Catalogue fictif quand Olist n'est pas disponible."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "product_id": [f"DEMO{i:05d}" for i in range(n_products)],
            "unit_price": np.round(rng.lognormal(mean=4.0, sigma=0.6, size=n_products), 2),
            "n_sold": rng.geometric(p=0.15, size=n_products),
        }
    )


def generate_business_data(
    products: pd.DataFrame,
    seed: int = 42,
    snapshot_date: str = DEFAULT_SNAPSHOT_DATE,
) -> pd.DataFrame:
    """Construit le dataset 'Product Business Data' (coûts, stock, délais)."""
    rng = np.random.default_rng(seed)
    n = len(products)
    price = products["unit_price"].to_numpy(dtype=float)

    # Coûts : entre 45 % et 80 % du prix de vente, + petits frais annexes
    purchase_cost = np.round(price * rng.uniform(0.45, 0.80, n), 2)
    other_costs = np.round(price * rng.uniform(0.0, 0.08, n), 2)
    min_margin = rng.choice([0.10, 0.15, 0.20, 0.25], size=n, p=[0.20, 0.35, 0.30, 0.15])
    lead_time = rng.integers(3, 31, size=n)

    # Demande de référence sur 30 jours (au moins 0.5 pour éviter les zéros partout)
    d30 = np.maximum(products["n_sold"].to_numpy(dtype=float) / OLIST_HISTORY_DAYS * 30, 0.5)

    profile = rng.choice(PROFILES, size=n, p=PROFILE_PROBS)
    stock = np.zeros(n, dtype=int)

    healthy = profile == "healthy"
    over = profile == "overstock"
    low = profile == "low_stock"
    stock[healthy] = np.ceil(d30[healthy] * rng.uniform(0.8, 2.0, healthy.sum())) + 1
    stock[over] = np.ceil(d30[over] * rng.uniform(6.0, 15.0, over.sum())) + 10
    stock[low] = np.floor(d30[low] * rng.uniform(0.1, 0.4, low.sum()))

    return pd.DataFrame(
        {
            "product_id": products["product_id"].to_numpy(),
            "reference_unit_price": np.round(price, 2),
            "purchase_cost": purchase_cost,
            "other_unit_costs": other_costs,
            "min_margin_pct": min_margin,
            "lead_time_days": lead_time,
            "current_stock": stock,
            "inventory_date": snapshot_date,
            "synthetic_profile": profile,
            "is_synthetic": True,
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Génère des données business synthétiques.")
    parser.add_argument("--olist-dir", default=None, help="Dossier des CSV Olist (optionnel)")
    parser.add_argument("--n-products", type=int, default=200, help="Taille du mode démo")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--snapshot-date", default=DEFAULT_SNAPSHOT_DATE)
    parser.add_argument(
        "--out", default="data/processed/product_business_data.csv", help="Fichier de sortie"
    )
    args = parser.parse_args()

    if args.olist_dir:
        products = load_olist_products(args.olist_dir)
        source = f"Olist ({len(products)} produits)"
    else:
        products = make_demo_products(args.n_products, args.seed)
        source = f"catalogue démo ({len(products)} produits)"

    df = generate_business_data(products, seed=args.seed, snapshot_date=args.snapshot_date)
    ensure_valid_product_business_data(df)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"OK : {len(df)} lignes générées depuis {source} -> {out}")
    print(df["synthetic_profile"].value_counts().to_string())


if __name__ == "__main__":
    main()
