# 1. Qué se construyó

## Mapa de archivos

```
agente-inventoria/
├── agent.py                 El agente: el bucle y la interfaz de terminal (CLI)
├── agent_lib/
│   ├── tools.py             Las 5 tools: esquemas para el LLM + funciones que llaman a la API
│   └── logger.py            Escribe cada evento en conversation_log.csv (solo añade)
├── api/
│   ├── app.py               Los endpoints de FastAPI y el manejo de errores HTTP
│   ├── models.py            Modelos Pydantic: forma y validación de lo que entra y sale
│   └── storage.py           Lectura/escritura de products.csv y excepciones de negocio
├── tests/                   Tests automáticos con pytest (API, log y bucle del agente)
├── ejemplos/                Un log real de una sesión, como muestra (el log de verdad está en .gitignore)
├── data/                    (se crea sola al ejecutar; está en .gitignore)
│   ├── products.csv         El inventario (persistencia)
│   └── conversation_log.csv El historial de eventos del agente
├── .env.example             Plantilla de configuración (el .env real NO se sube al repo)
├── .gitignore               Excluye .env, .venv y los CSV generados
├── pyproject.toml           Dependencias para uv (y las de desarrollo: pytest)
├── uv.lock                  Versiones exactas instaladas, para reproducir el entorno
├── requirements.txt         Las mismas dependencias, por si no hay uv
└── README.md                Instalación y arranque
```

También se **eliminaron** los archivos del template inicial del repositorio (`main.py`,
`server.py`, `learn.json`, `README.es.md`), porque eran un "Hello World" de un curso y no
tenían relación con este proyecto.

## Las dos mitades del sistema

```
   Tú (terminal)                  Groq (LLM en la nube)
        │                                ▲
        ▼                                │ (historial + tools)
  ┌───────────┐   pedido HTTP    ┌───────┴───────┐
  │ agent.py  │ ───────────────► │  api/app.py   │ ──► data/products.csv
  │ (el bucle)│ ◄─────────────── │  (FastAPI)    │
  └─────┬─────┘   respuesta JSON └───────────────┘
        │
        └──► data/conversation_log.csv   (cada evento, solo se añade)
```

**Idea clave:** el LLM nunca toca el CSV. Solo puede pedir "ejecuta esta tool con estos
argumentos"; el agente es quien hace el pedido HTTP a la API, y la API es la única que lee y
escribe el inventario. Así hay **una sola fuente de verdad**.

## Qué pasa cuando escribes "vendimos 12 bolsas de arábica"

1. `agent.py` lee la frase, la guarda en el historial y en `conversation_log.csv`.
2. Manda al LLM el historial completo y la lista de tools.
3. El LLM responde: "quiero ejecutar `buscar_producto` con `consulta='arábica'`".
4. El agente hace `GET /products/search?q=arábica`, recibe los productos y los añade al
   historial.
5. Vuelve a llamar al LLM, que ahora ve los productos y pide `ajustar_stock` con `delta=-12`.
6. El agente hace `PATCH /inventory/bolsas-de-arabica-1kg`; la API resta y guarda el CSV.
7. El resultado vuelve al historial. El LLM ya no pide más tools y redacta la respuesta final.
8. El agente la imprime y la registra en el log.

## El catálogo

Como se pidió creatividad, el catálogo de ejemplo es el de una **cafetería** (10 productos):
café arábica y robusta, leche de avena y entera, azúcar, vasos, tapas, servilletas, cacao y
bolsas de arábica de 1 kg. Se genera solo la primera vez que arranca la API.

## Los endpoints

| Método | Ruta | Para qué |
|---|---|---|
| GET | `/inventory` | Lista completa |
| POST | `/inventory` | Crear producto (`name`, `quantity`, `unit`) |
| PATCH | `/inventory/{id}` | Ajustar stock con un `delta` (positivo entra, negativo sale) |
| GET | `/inventory/alerts?threshold=10` | Productos por debajo de un umbral |
| GET | `/products/search?q=...` | Buscar por nombre |
| GET | `/products`, `/products/{id}`, `/products/low-stock` | Consultas adicionales |
| POST | `/products`, PATCH `/products/{id}/quantity` | Equivalentes a los de `/inventory` |
| GET | `/health` | Comprobar que la API está viva (siempre abierto) |
| GET | `/` | Redirige a `/docs` |

Con la API arrancada, la documentación interactiva está en `http://localhost:8000/docs`.
