# Agente de Inventario

Sistema de inventario con dos partes que trabajan juntas:

- **`api/`** — API REST con FastAPI. Lista productos, crea nuevos, actualiza cantidades y
  avisa de stock bajo. Todo se guarda en `data/products.csv`.
- **`agent.py`** — Agente de IA que entiende lenguaje natural ("llegaron 30 unidades de leche
  de avena", "vendimos 12 bolsas de arábica", "¿qué productos están por agotarse?"), decide qué
  endpoint de la API llamar, y responde como una conversación.

> Para entender las decisiones de diseño, el bucle del agente y el glosario de términos,
> mira la carpeta [aprendiendo con la ia/](aprendiendo%20con%20la%20ia/README.md).

## Instalación

Con [uv](https://docs.astral.sh/uv/):

```bash
uv add fastapi uvicorn openai python-dotenv
```

(o, sin uv: `pip install -r requirements.txt`). Si clonás este repo, con `uv sync` se instala
todo lo declarado en `pyproject.toml` y `uv.lock`. Ese comando `uv add` es el conjunto completo
de dependencias del proyecto: el agente habla con la API usando solo la biblioteca estándar.

Después ejecutá los comandos con `uv run` (por ejemplo `uv run uvicorn api.app:app --reload`), o
activá el entorno con `source .venv/bin/activate`.

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

## Tests

Los tests usan CSV temporales y un LLM simulado: no gastan créditos ni tocan tus datos.

```bash
uv run pytest      # o, con el entorno activo: pip install pytest httpx jsonschema && pytest
```

Cubren los endpoints y sus errores (404, 409, 400, 422, 401), la búsqueda con erratas, el
registro de solo adición, y el bucle del agente (varios pasos, corte por respuesta final, tope de
iteraciones, API caída).

## Proteger la API con una clave (opcional)

Por defecto la API queda abierta, pensada para uso local. Si la exponés a internet (por ejemplo
con el puerto público de Codespaces), definí en `.env`:

```
API_KEY=una_clave_larga_y_aleatoria
```

Entonces `/inventory` y `/products` exigen la cabecera `X-API-Key` (401 si falta o es incorrecta),
y el agente la envía solo. `/health` y `/docs` siguen abiertos. Las dos terminales leen el mismo
`.env`, así que basta con reiniciar la API y el agente.

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
`data/conversation_log.csv` con columnas `actor, message, tool_call, timestamp`. Ese archivo es
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
