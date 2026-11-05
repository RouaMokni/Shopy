"""Validation des données business produit (coûts, stock, délais)."""

from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS = [
    "product_id",
    "reference_unit_price",
    "purchase_cost",
    "other_unit_costs",
    "min_margin_pct",
    "lead_time_days",
    "current_stock",
    "inventory_date",
    "synthetic_profile",
    "is_synthetic",
]


class DataValidationError(ValueError):
    """Levée quand un jeu de données ne respecte pas le schéma attendu."""


def find_product_business_data_issues(df: pd.DataFrame) -> list[str]:
    """Retourne la liste des problèmes détectés (liste vide = données valides)."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return [f"Colonnes manquantes : {missing}"]

    issues: list[str] = []

    if df[REQUIRED_COLUMNS].isna().any().any():
        cols = df[REQUIRED_COLUMNS].columns[df[REQUIRED_COLUMNS].isna().any()].tolist()
        issues.append(f"Valeurs manquantes dans : {cols}")
        return issues  # les contrôles suivants supposent l'absence de NaN

    if df["product_id"].duplicated().any():
        issues.append("product_id dupliqués")

    if (df["purchase_cost"] <= 0).any():
        issues.append("purchase_cost doit être > 0")
    if (df["other_unit_costs"] < 0).any():
        issues.append("other_unit_costs doit être >= 0")
    if (df["reference_unit_price"] <= 0).any():
        issues.append("reference_unit_price doit être > 0")

    total_cost = df["purchase_cost"] + df["other_unit_costs"]
    if (total_cost >= df["reference_unit_price"]).any():
        issues.append("Coût total >= prix de référence (marge nulle ou négative)")

    if ((df["min_margin_pct"] <= 0) | (df["min_margin_pct"] >= 1)).any():
        issues.append("min_margin_pct doit être strictement entre 0 et 1")

    if (df["lead_time_days"] <= 0).any():
        issues.append("lead_time_days doit être > 0")

    if (df["current_stock"] < 0).any():
        issues.append("current_stock doit être >= 0")

    if not df["is_synthetic"].astype(bool).all():
        issues.append("is_synthetic doit être True pour toutes les lignes générées")

    return issues


def ensure_valid_product_business_data(df: pd.DataFrame) -> None:
    """Lève DataValidationError si le DataFrame n'est pas valide."""
    issues = find_product_business_data_issues(df)
    if issues:
        raise DataValidationError(" | ".join(issues))
