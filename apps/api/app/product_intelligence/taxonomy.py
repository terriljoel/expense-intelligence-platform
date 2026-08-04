from __future__ import annotations

from app.services.text_normalization import normalize_product_name


FAMILIES = (
    ("Milk", "Dairy", ("milch", "milk", "vollmilch", "h-milch")),
    ("Pizza", "Prepared food", ("pizza", "pizzetta")),
    ("Yogurt", "Dairy", ("joghurt", "yogurt", "yoghurt")),
    ("Cheese", "Dairy", ("käse", "kaese", "cheese", "mozzarella")),
    ("Bread", "Bakery", ("brot", "bread", "brötchen", "broetchen")),
    ("Pasta", "Pantry", ("nudeln", "pasta", "spaghetti", "penne")),
    ("Rice", "Pantry", ("reis", "rice")),
    ("Coffee", "Beverages", ("kaffee", "coffee", "espresso")),
    ("Tea", "Beverages", ("tee", "tea")),
    ("Water", "Beverages", ("wasser", "water")),
)


def infer_family(*values: str | None) -> tuple[str | None, str | None]:
    text = normalize_product_name(" ".join(value for value in values if value))
    tokens = set(text.split())
    for family, category, keywords in FAMILIES:
        if any(keyword in tokens or keyword in text for keyword in keywords):
            return family, category
    return None, None
