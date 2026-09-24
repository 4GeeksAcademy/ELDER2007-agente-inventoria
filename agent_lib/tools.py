"""Herramientas (tools) que el agente expone al LLM.

Cada tool es un envoltorio 1:1 sobre un endpoint de la API REST de inventario:

    listar_productos     -> GET  /inventory
    buscar_producto      -> GET  /products/search
    productos_bajo_stock -> GET  /inventory/alerts
    crear_producto       -> POST /inventory
    ajustar_stock        -> PATCH /inventory/{id}

El LLM nunca toca el CSV directamente: siempre pasa por la API, que es la
única fuente de verdad. Cada tool declara su `name`, `description` y
`parameters` (JSON Schema) siguiendo el formato de function-calling de
OpenAI/Groq, con tipos y restricciones explícitas para que el modelo no
tenga que adivinar qué mandar.
"""
import os
from typing import Optional

import requests

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "listar_productos",
            "description": (
                "Lista todos los productos del inventario con su cantidad, unidad y umbral "
                "mínimo actuales. Llama a GET /inventory. No recibe parámetros."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_producto",
            "description": (
                "Busca productos por nombre (coincidencia parcial, ignora acentos y mayúsculas). "
                "Llama a GET /products/search?q=. Úsala SIEMPRE antes de ajustar stock o crear un "
                "producto, para saber si ya existe y obtener su id exacto."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {
                        "type": "string",
                        "description": "Texto a buscar en el nombre del producto, p. ej. 'leche de avena' o 'arábica'.",
                        "minLength": 1,
                    }
                },
                "required": ["consulta"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "productos_bajo_stock",
            "description": (
                "Devuelve los productos cuya cantidad está por debajo de un umbral. Llama a "
                "GET /inventory/alerts. Si no se pasa 'umbral', la API usa 10 por defecto."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "umbral": {
                        "type": "number",
                        "description": "Cantidad mínima aceptable; se listan los productos por debajo de este valor. Opcional, default 10.",
                        "minimum": 0,
                    }
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crear_producto",
            "description": (
                "Crea un producto nuevo en el inventario. Llama a POST /inventory. Solo debe "
                "usarse cuando 'buscar_producto' confirma que el producto no existe todavía."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {
                        "type": "string",
                        "description": "Nombre del producto, p. ej. 'Leche de avena'.",
                        "minLength": 1,
                    },
                    "cantidad": {
                        "type": "number",
                        "description": "Cantidad inicial en stock.",
                        "minimum": 0,
                    },
                    "unidad": {
                        "type": "string",
                        "description": "Unidad de medida: unidades, kg, litros, bolsas, paquetes, etc.",
                        "minLength": 1,
                    },
                    "categoria": {
                        "type": "string",
                        "description": "Categoría del producto. Opcional, default 'general'.",
                    },
                    "stock_minimo": {
                        "type": "number",
                        "description": "Umbral para considerar 'stock bajo'. Opcional, default 5.",
                        "minimum": 0,
                    },
                },
                "required": ["nombre", "cantidad", "unidad"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ajustar_stock",
            "description": (
                "Suma o resta una cantidad al stock de un producto existente. Llama a "
                "PATCH /inventory/{id}. Usa delta positivo cuando llega mercadería y delta "
                "negativo cuando se vende o se da de baja. Requiere el id exacto del producto "
                "(usa 'buscar_producto' primero). Si el delta dejaría el stock en negativo, la "
                "API rechaza el ajuste."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "producto_id": {
                        "type": "string",
                        "description": "id exacto del producto, obtenido de 'buscar_producto'.",
                        "minLength": 1,
                    },
                    "delta": {
                        "type": "number",
                        "description": "Cambio de cantidad: positivo si entra mercadería, negativo si sale.",
                    },
                    "motivo": {
                        "type": "string",
                        "description": "Motivo breve del ajuste, p. ej. 'venta' o 'llegada de proveedor'. Opcional.",
                    },
                },
                "required": ["producto_id", "delta"],
                "additionalProperties": False,
            },
        },
    },
]


def _request(method: str, path: str, **kwargs) -> dict:
    response = requests.request(method, f"{API_BASE_URL}{path}", timeout=10, **kwargs)
    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        return {"error": True, "status_code": response.status_code, "detail": detail}
    return response.json()


def listar_productos() -> dict:
    return {"productos": _request("GET", "/inventory")}


def buscar_producto(consulta: str) -> dict:
    return {"resultados": _request("GET", "/products/search", params={"q": consulta})}


def productos_bajo_stock(umbral: Optional[float] = None) -> dict:
    params = {"threshold": umbral} if umbral is not None else None
    return {"productos_bajo_stock": _request("GET", "/inventory/alerts", params=params)}


def crear_producto(
    nombre: str,
    cantidad: float,
    unidad: str,
    categoria: Optional[str] = None,
    stock_minimo: Optional[float] = None,
) -> dict:
    payload = {"name": nombre, "quantity": cantidad, "unit": unidad}
    if categoria is not None:
        payload["category"] = categoria
    if stock_minimo is not None:
        payload["min_stock"] = stock_minimo
    return _request("POST", "/inventory", json=payload)


def ajustar_stock(producto_id: str, delta: float, motivo: Optional[str] = None) -> dict:
    return _request("PATCH", f"/inventory/{producto_id}", json={"delta": delta, "reason": motivo})


TOOL_IMPLEMENTATIONS = {
    "listar_productos": listar_productos,
    "buscar_producto": buscar_producto,
    "productos_bajo_stock": productos_bajo_stock,
    "crear_producto": crear_producto,
    "ajustar_stock": ajustar_stock,
}
