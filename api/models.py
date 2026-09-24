"""Modelos Pydantic para el inventario."""
from typing import Optional

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, description="Nombre del producto, p. ej. 'Leche de avena'")
    quantity: float = Field(..., ge=0, description="Cantidad inicial en stock")
    unit: str = Field(..., min_length=1, description="Unidad de medida: unidades, kg, litros, bolsas, etc.")
    category: str = Field("general", description="Categoría del producto")
    min_stock: float = Field(5, ge=0, description="Umbral para considerar 'stock bajo'")


class QuantityAdjustment(BaseModel):
    delta: float = Field(..., description="Cambio de cantidad: positivo si entra mercadería, negativo si sale")
    reason: Optional[str] = Field(None, description="Motivo del ajuste, p. ej. 'venta', 'llegada de proveedor'")


class Product(BaseModel):
    id: str
    name: str
    category: str
    quantity: float
    unit: str
    min_stock: float
    updated_at: str

    @property
    def low_stock(self) -> bool:
        return self.quantity <= self.min_stock
