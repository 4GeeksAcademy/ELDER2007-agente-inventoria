"""API REST de inventario.

Arranque:
    uvicorn api.app:app --reload
"""
import logging
import os
import secrets
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import APIKeyHeader

from api import storage
from api.models import Product, ProductCreate, QuantityAdjustment
from api.storage import InsufficientStockError, ProductAlreadyExistsError, ProductNotFoundError

load_dotenv()

logger = logging.getLogger("inventoria")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(x_api_key: Optional[str] = Depends(api_key_header)) -> None:
    """Si API_KEY está definida en el entorno, exige la cabecera X-API-Key. Si no, la API queda abierta."""
    expected = os.getenv("API_KEY")
    if expected and not (x_api_key and secrets.compare_digest(x_api_key, expected)):
        raise HTTPException(status_code=401, detail="API key inválida o ausente. Envía la cabecera X-API-Key.")


protected = APIRouter(dependencies=[Depends(verify_api_key)])

app = FastAPI(
    title="Inventoria API",
    description="API de inventario con persistencia en CSV",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Cualquier error no previsto responde con JSON consistente en vez de un 500 en texto plano."""
    logger.exception("Error no manejado en %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor. Intentá de nuevo en un momento."})


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
def health():
    return {"status": "ok"}


@protected.get("/inventory", response_model=List[Product])
def get_inventory():
    """Devuelve la lista completa de productos del inventario."""
    return storage.list_products()


@protected.post("/inventory", response_model=Product, status_code=201)
def add_inventory_product(data: ProductCreate):
    """Añade un nuevo producto al inventario (name, quantity, unit)."""
    try:
        return storage.create_product(data)
    except ProductAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@protected.get("/inventory/alerts", response_model=List[Product])
def inventory_alerts(threshold: float = Query(10, ge=0, description="Umbral de cantidad para la alerta")):
    """Productos cuya cantidad está por debajo del umbral dado (por defecto 10)."""
    return [p for p in storage.list_products() if p.quantity < threshold]


@protected.get("/products", response_model=List[Product])
def list_products(low_stock: bool = Query(False, description="Filtrar solo productos con stock bajo")):
    products = storage.list_products()
    if low_stock:
        products = [p for p in products if p.low_stock]
    return products


@protected.get("/products/low-stock", response_model=List[Product])
def low_stock_products():
    """Productos que están por agotarse (cantidad <= umbral mínimo)."""
    return storage.get_low_stock()


@protected.get("/products/search", response_model=List[Product])
def search_products(q: str = Query(..., min_length=1, description="Texto a buscar en el nombre del producto")):
    return storage.search(q)


@protected.get("/products/{product_id}", response_model=Product)
def get_product(product_id: str):
    product = storage.get_by_id(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Producto '{product_id}' no encontrado")
    return product


@protected.post("/products", response_model=Product, status_code=201)
def create_product(data: ProductCreate):
    try:
        return storage.create_product(data)
    except ProductAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@protected.patch("/products/{product_id}/quantity", response_model=Product)
def adjust_quantity(product_id: str, adjustment: QuantityAdjustment):
    try:
        return storage.adjust_quantity(product_id, adjustment.delta)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InsufficientStockError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@protected.patch("/inventory/{product_id}", response_model=Product)
def adjust_inventory_stock(product_id: str, adjustment: QuantityAdjustment):
    """Actualiza el stock de un producto existente (delta positivo o negativo)."""
    try:
        return storage.adjust_quantity(product_id, adjustment.delta)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InsufficientStockError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


app.include_router(protected)
