"""Persistencia del inventario en un archivo CSV.

Cada operación lee el CSV completo, aplica el cambio y vuelve a escribirlo.
Para el volumen de un inventario de una tienda esto es simple, legible y
suficientemente rápido; un `Lock` evita condiciones de carrera entre
requests concurrentes.
"""
import csv
import re
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from api.models import Product, ProductCreate

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "products.csv"
FIELDNAMES = ["id", "name", "category", "quantity", "unit", "min_stock", "updated_at"]

_lock = threading.Lock()


class ProductNotFoundError(Exception):
    """No existe un producto con el id dado."""


class ProductAlreadyExistsError(Exception):
    """Ya existe un producto con el mismo id (nombre normalizado)."""


class InsufficientStockError(Exception):
    """El ajuste solicitado dejaría la cantidad del producto en negativo."""

SEED_PRODUCTS = [
    {"name": "Café arábica", "category": "Café", "quantity": 40, "unit": "kg", "min_stock": 10},
    {"name": "Café robusta", "category": "Café", "quantity": 25, "unit": "kg", "min_stock": 8},
    {"name": "Leche de avena", "category": "Lácteos y alternativas", "quantity": 18, "unit": "litros", "min_stock": 12},
    {"name": "Leche entera", "category": "Lácteos y alternativas", "quantity": 30, "unit": "litros", "min_stock": 15},
    {"name": "Azúcar blanca", "category": "Insumos", "quantity": 20, "unit": "kg", "min_stock": 5},
    {"name": "Vasos de cartón 12oz", "category": "Descartables", "quantity": 300, "unit": "unidades", "min_stock": 100},
    {"name": "Tapas para vaso 12oz", "category": "Descartables", "quantity": 280, "unit": "unidades", "min_stock": 100},
    {"name": "Servilletas", "category": "Descartables", "quantity": 15, "unit": "paquetes", "min_stock": 10},
    {"name": "Cacao en polvo", "category": "Insumos", "quantity": 6, "unit": "kg", "min_stock": 4},
    {"name": "Bolsas de arábica 1kg", "category": "Café", "quantity": 14, "unit": "bolsas", "min_stock": 6},
]


def _slugify(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug or "producto"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_product(row: dict) -> Product:
    return Product(
        id=row["id"],
        name=row["name"],
        category=row["category"],
        quantity=float(row["quantity"]),
        unit=row["unit"],
        min_stock=float(row["min_stock"]),
        updated_at=row["updated_at"],
    )


def _ensure_csv() -> None:
    if CSV_PATH.exists():
        return
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for item in SEED_PRODUCTS:
            writer.writerow(
                {
                    "id": _slugify(item["name"]),
                    "name": item["name"],
                    "category": item["category"],
                    "quantity": item["quantity"],
                    "unit": item["unit"],
                    "min_stock": item["min_stock"],
                    "updated_at": _now(),
                }
            )


def _read_all_rows() -> List[dict]:
    _ensure_csv()
    with CSV_PATH.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_all_rows(rows: List[dict]) -> None:
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def list_products() -> List[Product]:
    with _lock:
        rows = _read_all_rows()
    return [_row_to_product(r) for r in rows]


def get_low_stock() -> List[Product]:
    return [p for p in list_products() if p.low_stock]


def get_by_id(product_id: str) -> Optional[Product]:
    for p in list_products():
        if p.id == product_id:
            return p
    return None


def search(query: str) -> List[Product]:
    """Búsqueda flexible por nombre: coincidencia parcial, sin distinguir mayúsculas/acentos."""
    def normalize(text: str) -> str:
        return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()

    needle = normalize(query)
    results = []
    for p in list_products():
        haystack = normalize(p.name)
        if needle in haystack or haystack in needle:
            results.append(p)
    if not results:
        # fallback: coincidencia por palabras sueltas (p. ej. "arábica" -> "Café arábica")
        needle_words = set(needle.split())
        for p in list_products():
            haystack_words = set(normalize(p.name).split())
            if needle_words & haystack_words:
                results.append(p)
    return results


def create_product(data: ProductCreate) -> Product:
    with _lock:
        rows = _read_all_rows()
        product_id = _slugify(data.name)
        if any(r["id"] == product_id for r in rows):
            raise ProductAlreadyExistsError(f"El producto '{data.name}' ya existe (id={product_id})")
        row = {
            "id": product_id,
            "name": data.name,
            "category": data.category,
            "quantity": data.quantity,
            "unit": data.unit,
            "min_stock": data.min_stock,
            "updated_at": _now(),
        }
        rows.append(row)
        _write_all_rows(rows)
    return _row_to_product(row)


def adjust_quantity(product_id: str, delta: float) -> Product:
    with _lock:
        rows = _read_all_rows()
        for row in rows:
            if row["id"] == product_id:
                current = float(row["quantity"])
                new_quantity = current + delta
                if new_quantity < 0:
                    raise InsufficientStockError(
                        f"Stock insuficiente para '{row['name']}': hay {current} {row['unit']} "
                        f"disponibles y se intentó restar {abs(delta)}."
                    )
                row["quantity"] = new_quantity
                row["updated_at"] = _now()
                _write_all_rows(rows)
                return _row_to_product(row)
    raise ProductNotFoundError(f"Producto '{product_id}' no encontrado")
