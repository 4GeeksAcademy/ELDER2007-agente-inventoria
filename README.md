# Agente de Inventario

Sistema de inventario con dos partes que trabajan juntas:

- **`api/`** — API REST con FastAPI. Lista productos, crea nuevos, actualiza cantidades y
  avisa de stock bajo. Todo se guarda en `data/products.csv`.
- **`agent.py`** — Agente de IA que entiende lenguaje natural ("llegaron 30 unidades de leche
  de avena", "vendimos 12 bolsas de arábica", "¿qué productos están por agotarse?"), decide qué
  endpoint de la API llamar, y responde como una conversación.

## Instalación

Con [uv](https://docs.astral.sh/uv/):

```bash
uv add fastapi uvicorn openai python-dotenv
```

(o, sin uv: `pip install -r requirements.txt`)

Copiá `.env.example` a `.env` y completá tu clave de [Groq](https://console.groq.com/keys):

```bash
cp .env.example .env
```

```
GROQ_API_KEY=tu_clave
```

`.env` está en `.gitignore`: nunca se sube al repo.

## Arranque

**Importante: la API tiene que estar corriendo *antes* de iniciar el agente.** El agente no
guarda nada por su cuenta — cada tool que usa (`listar_productos`, `crear_producto`,
`ajustar_stock`, etc.) le hace un pedido HTTP a la API. Si la API no está arriba, esos pedidos
fallan y el agente te va a avisar del error en vez de poder ayudarte.

**Terminal 1 — arrancá primero la API:**

```bash
uvicorn api.app:app --reload
```

Esperá a ver `Application startup complete.` en la terminal, o confirmá que responde entrando a
`http://localhost:8000/health` (debería devolver `{"status":"ok"}`).

**Terminal 2 — con la API ya arriba, arrancá el agente:**

```bash
python agent.py
```

Escribí pedidos en lenguaje natural y listo. Para salir, `Ctrl+C` en cada terminal (no importa
el orden en que los cierres).

El agente se puede reiniciar en cualquier momento sin tocar la API: todo el inventario y el
historial de conversación quedan en los CSV de `data/`, así que no se pierde nada. Si necesitás
reiniciar la API, el agente va a fallar en la próxima tool que intente usar hasta que la vuelvas
a levantar — no hace falta reiniciar el agente también.

## Cómo funciona el agente

Por cada mensaje del usuario, el agente sigue este ciclo:

1. **Observar** — recibe el mensaje en lenguaje natural.
2. **Pensar** — se lo manda al LLM (Groq) junto con la lista de herramientas disponibles
   (`listar_productos`, `buscar_producto`, `productos_bajo_stock`, `crear_producto`,
   `ajustar_stock`) y todo el historial de la sesión.
3. **Actuar** — si el LLM pide usar una herramienta, el agente llama al endpoint
   correspondiente de la API.
4. **Actualizar** — el resultado se agrega al historial y se vuelve a pensar, hasta que el LLM
   da una respuesta final (sin más llamadas a herramientas).

Todo el historial vive en memoria durante la sesión, y cada evento (mensaje del usuario,
llamada a herramienta, resultado, respuesta del agente) además se registra en
`data/conversation_log.csv` con columnas `timestamp, actor, message, tool_call`. Ese archivo es
**append-only**: nunca se sobrescribe, solo se agregan filas nuevas.

## API

| Método | Endpoint                         | Qué hace                                      |
| ------ | --------------------------------- | ---------------------------------------------- |
| GET    | `/inventory`                      | Devuelve la lista completa de productos        |
| POST   | `/inventory`                      | Añade un nuevo producto (`name`, `quantity`, `unit`) |
| GET    | `/inventory/alerts`               | Productos con cantidad por debajo de `?threshold=` (default 10) |
| PATCH  | `/inventory/{id}`                 | Actualiza stock (`delta` positivo entra, negativo sale) |
| GET    | `/products`                       | Lista todos los productos (`?low_stock=true` filtra) |
| GET    | `/products/low-stock`             | Productos por agotarse                         |
| GET    | `/products/search?q=...`          | Busca productos por nombre                     |
| GET    | `/products/{id}`                  | Detalle de un producto                         |
| POST   | `/products`                       | Crea un producto nuevo                         |
| PATCH  | `/products/{id}/quantity`         | Ajusta cantidad (`delta` positivo o negativo)  |

Cada producto tiene: `name`, `category`, `quantity`, `unit` (unidades, kg, litros, bolsas...),
`min_stock` (umbral de stock bajo) y `updated_at`.

Documentación interactiva de la API una vez arrancada: `http://localhost:8000/docs`.

## Catálogo inicial

`data/products.csv` se crea solo la primera vez que arranca la API, con un catálogo de
ejemplo pensado para una cafetería (café arábica y robusta, leche de avena y entera, azúcar,
descartables, etc.). Se puede editar el CSV a mano o dejar que el agente lo vaya actualizando.
