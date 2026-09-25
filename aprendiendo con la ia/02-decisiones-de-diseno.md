# 2. Decisiones de diseño

Cada decisión sigue el mismo formato: **qué se eligió**, **qué alternativas había** y
**por qué**. Al final de cada una hay un *coste* cuando la decisión tiene una desventaja real.

---

## A. La API

### A1. Persistencia en CSV con el módulo `csv`, sin pandas ni base de datos
- **Elegido:** `csv.DictReader` / `csv.DictWriter` de la librería estándar.
- **Alternativas:** pandas, SQLite.
- **Por qué:** el enunciado exigía CSV y una lista de dependencias concreta que no incluía
  pandas. Para unas decenas de productos, leer y reescribir el archivo entero es simple y
  legible.
- **Coste:** cada operación lee y reescribe todo el archivo. No escalaría a miles de
  productos ni a varios procesos a la vez.

### A2. Un `Lock` alrededor de las operaciones de escritura
- **Elegido:** `threading.Lock()` en `storage.py`.
- **Por qué:** FastAPI puede atender dos peticiones a la vez. Sin candado, dos ajustes de
  stock simultáneos leerían el mismo valor y uno pisaría al otro (*race condition*).
- **Coste:** el candado solo protege dentro de **un** proceso. Si arrancaras uvicorn con
  varios *workers*, dejaría de bastar (habría que usar una base de datos).

### A3. El id del producto es un *slug* de su nombre
- **Elegido:** `"Leche de avena"` → `leche-de-avena` (sin acentos, minúsculas, guiones).
- **Alternativas:** un número autoincremental, un UUID.
- **Por qué:** el LLM habla con nombres, no con números. Un id legible ayuda a que el modelo
  lo maneje bien y a que tú lo entiendas al leer el log.
- **Coste:** dos nombres que producen el mismo slug (`"Té verde"` y `"te verde"`) chocan. La
  API lo detecta y responde 409. Además, renombrar un producto cambiaría su id.

### A4. `quantity` es `float`, no `int`
- **Por qué:** el enunciado pedía unidades como kg y litros, que admiten decimales (2,5 kg).

### A5. Dos conceptos de "stock bajo"
- `min_stock`: umbral **propio de cada producto** (los vasos avisan a 100, el cacao a 4).
  Lo usa `/products/low-stock`.
- `threshold`: umbral **global y configurable** en la petición, por defecto 10. Lo usa
  `/inventory/alerts`.
- **Por qué:** son dos preguntas distintas. "¿Qué está por debajo de su propio mínimo?" y
  "¿Qué queda por debajo de X unidades?". Se pidieron ambas en momentos distintos y las dos
  tienen sentido.

### A6. Rutas duplicadas: `/inventory` y `/products`
- **Qué pasó:** primero se hizo `/products`; después se pidieron los endpoints concretos
  bajo `/inventory`. Se **añadieron** sin borrar los anteriores.
- **Por qué no se borraron:** `/products/search` no tiene equivalente en `/inventory` y el
  agente lo necesita.
- **Coste honesto:** hay duplicación (`POST` y `PATCH` existen en ambos sitios). En un
  proyecto real convendría elegir un prefijo y quedarse solo con uno.

### A7. Errores HTTP con excepciones propias
- **Elegido:** `ProductNotFoundError` → 404, `ProductAlreadyExistsError` → 409,
  `InsufficientStockError` → 400. Validación de datos → 422 (lo hace Pydantic solo).
- **Alternativa descartada:** usar `KeyError` y `ValueError` de Python.
- **Por qué:** `str(KeyError("mensaje"))` devuelve el mensaje **con comillas extra**, y se
  veía `"\"Producto...\""` en la respuesta. Se descubrió probando (ver
  [05](05-problemas-y-limitaciones.md)). Además, `ValueError` servía para dos errores
  distintos y no se podían distinguir.

### A8. Vender más de lo que hay devuelve error (400), no se queda en 0
- **Antes:** el stock se recortaba a 0 sin avisar.
- **Ahora:** se rechaza con un mensaje ("hay 40.0 kg disponibles y se intentó restar 999").
- **Por qué:** recortar en silencio **oculta errores** (por ejemplo, un registro duplicado o
  un producto mal elegido). Es mejor fallar de forma visible. El mensaje llega al LLM, que
  puede explicárselo al usuario.

### A9. Un manejador global para errores inesperados
- **Por qué:** sin él, un fallo imprevisto devuelve texto plano. Con él, siempre es JSON con
  el formato `{"detail": "..."}`, igual que el resto de errores. No se expone el error
  interno al cliente; queda solo en el log del servidor.

---

## B. El agente

### B1. Bucle escrito a mano, sin frameworks
- **Elegido:** Python puro (un `for`, un `if`, funciones simples).
- **Descartado:** LangChain, LlamaIndex, AutoGen, etc.
- **Por qué:** fue un requisito explícito, y además es lo más didáctico: ves exactamente
  cómo funciona un agente, sin magia. Los frameworks son más útiles cuando ya entiendes lo
  que hacen por dentro.

### B2. El paquete `openai` como cliente, apuntando a Groq
- **Elegido:** `OpenAI(base_url="https://api.groq.com/openai/v1")`.
- **Por qué:** Groq ofrece una API compatible con la de OpenAI, y la instalación pedida
  incluía `openai`. El paquete aquí es solo un **cliente HTTP con tipos**; no tiene ninguna
  lógica de agente.

### B3. Modelo `openai/gpt-oss-120b`
- **Qué pasó:** el modelo elegido primero (`llama-3.3-70b-versatile`) daba error 404: no
  estaba disponible para tu cuenta. Se consultó la lista real de modelos de tu clave y se
  eligió uno que **soporta tool calling**.
- **Lección:** los modelos de los proveedores cambian. Por eso el modelo se puede cambiar con
  la variable `GROQ_MODEL` en `.env` sin tocar el código.

### B4. Las tools tienen nombres en español y traducen a los campos de la API
- `nombre`/`cantidad`/`unidad` (lo que ve el LLM) → `name`/`quantity`/`unit` (lo que espera la API).
- **Por qué:** toda la conversación es en español; nombres coherentes ayudan al modelo a
  elegir bien. La traducción vive en `tools.py`, una capa fina entre el LLM y la API.

### B5. Los errores de una tool se devuelven como datos, no como excepciones
- **Elegido:** si la API falla o está caída, `actuar()` captura el error y se lo entrega al
  LLM como resultado (`{"error": true, "detail": "..."}`).
- **Por qué:** así el agente **no se cae** y el LLM puede explicarle el problema al usuario
  o intentar otra cosa. Un agente robusto trata los fallos como información.

### B6. Tope de 8 iteraciones por turno (`MAX_TOOL_ITERATIONS`)
- **Por qué:** si el LLM entrara en un ciclo pidiendo tools sin parar, el bucle sería
  infinito y gastaría dinero. El tope es una **red de seguridad**; en uso normal se termina
  mucho antes, cuando el LLM responde sin pedir tools.

### B7. Historial en memoria + log en disco: dos cosas distintas
| | Historial (`history`) | Log (`conversation_log.csv`) |
|---|---|---|
| Dónde | Lista de Python en RAM | Archivo en disco |
| Para qué | Es el **contexto** que se le manda al LLM | Es el **registro** para auditar |
| Sobrevive a reiniciar el agente | No | Sí |

Esto responde al requisito "el agente puede reiniciarse y el CSV conserva todo". Nota: al
reiniciar, el LLM **no recuerda** la conversación anterior; solo queda el registro.

### B8. El *system prompt* contiene reglas de negocio
- Buscar el producto **antes** de ajustar o crear.
- "Llegaron/entraron" → delta positivo; "vendimos/salieron" → delta negativo.
- Si hay stock insuficiente, no reintentar inventando otro número.
- **Por qué:** el LLM no sabe cómo funciona tu negocio; se lo dices en el prompt. Es la forma
  más barata de guiar su comportamiento.

---

## C. El registro (`conversation_log.csv`)

- **Columnas:** `actor, message, tool_call, timestamp`, en el orden pedido.
- **`actor`:** `user`, `assistant` o `tool`.
- **`tool_call`:** un JSON con el nombre y los argumentos cuando el LLM pide una tool; el
  nombre de la tool en la fila de su resultado.
- **`timestamp`:** ISO 8601 en **UTC** (`2026-09-24T18:08:13+00:00`). UTC evita ambigüedades
  con zonas horarias y horario de verano.
- **Solo añade:** el archivo se abre en modo `"a"` (append). La única vez que se abre en modo
  `"w"` es para crear la cabecera si el archivo no existe.

---

## D. Higiene del repositorio

- **`.env` en `.gitignore`:** una clave de API subida a GitHub se puede robar y usar en
  minutos. Se sube `.env.example` (sin secretos) como plantilla.
- **CSV generados en `.gitignore`:** son datos de ejecución, no código. La API los recrea.
- **La carpeta se llama `agent_lib`, no `agent`:** ya existe `agent.py`; un paquete `agent/`
  con el mismo nombre crearía ambigüedad al importar.
- **`pyproject.toml` y `requirements.txt`:** el primero para `uv`, el segundo por si no lo
  tienes instalado (en el entorno donde se desarrolló no había `uv`).
