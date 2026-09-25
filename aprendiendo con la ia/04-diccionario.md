# 4. Diccionario

"Diccionario" puede significar tres cosas en este proyecto, así que están las tres:

1. [Glosario de términos](#1-glosario-de-términos): qué significa cada palabra técnica.
2. [Diccionarios de Python (`dict`)](#2-diccionarios-de-python-dict-usados-en-el-proyecto): qué
   diccionarios se usan y por qué.
3. [Diccionario de datos](#3-diccionario-de-datos): qué campos tiene cada dato guardado.

---

## 1. Glosario de términos

**Agente (de IA)**: programa donde un LLM decide qué acción tomar, la ejecuta, observa el
resultado y repite hasta terminar. Se distingue de un simple chatbot en que **actúa**.

**LLM** (*Large Language Model*): el modelo de lenguaje. Aquí es `gpt-oss-120b`, alojado en
Groq. Recibe texto y devuelve texto (o una petición de usar una tool).

**Groq**: empresa que aloja modelos y los sirve por API a gran velocidad.

**Tool / function calling**: mecanismo por el que le describes funciones al LLM y él, en lugar
de responder con texto, puede pedirte que ejecutes una con ciertos argumentos. **El LLM no
ejecuta nada**: solo pide. Ejecutar es trabajo del agente.

**`tool_call`**: la petición concreta del LLM: nombre de la tool + argumentos.

**`tool_call_id`**: identificador de un `tool_call`. El resultado se devuelve con el mismo id
para que el LLM sepa a cuál corresponde.

**System prompt**: instrucciones fijas al inicio del historial que definen el rol y las reglas
del agente.

**Historial (*context*)**: la lista de mensajes que se envía al LLM en cada llamada. El LLM no
guarda memoria entre llamadas.

**Bucle del agente**: el ciclo Observar → Pensar → Actuar → Actualizar → Repetir.

**Framework de agentes**: librería que implementa el bucle por ti (LangChain, etc.). Aquí no se
usa ninguno.

**SDK / cliente**: librería que facilita hablar con una API. `openai` es un SDK.

**JSON Schema**: formato para describir la forma de un JSON (tipos, campos obligatorios,
mínimos). Así se describen los parámetros de cada tool.

**API REST**: servicio web que expone operaciones mediante rutas HTTP y verbos.

**Endpoint**: una ruta concreta de la API, por ejemplo `GET /inventory`.

**Verbos HTTP**: `GET` (leer), `POST` (crear), `PATCH` (modificar una parte).

**Códigos de estado HTTP**: número que resume el resultado. Los usados aquí:

| Código | Significado | Cuándo aparece |
|---|---|---|
| 200 | OK | Consulta o ajuste correcto |
| 201 | Creado | Se añadió un producto |
| 400 | Petición incorrecta | Stock insuficiente |
| 404 | No encontrado | El producto no existe |
| 409 | Conflicto | El producto ya existe |
| 422 | No procesable | Datos inválidos (falta un campo, cantidad negativa...) |
| 500 | Error del servidor | Fallo inesperado |

**FastAPI**: framework web de Python para construir APIs.

**Uvicorn**: el servidor que ejecuta la aplicación FastAPI.

**Pydantic**: librería que valida datos según un modelo. FastAPI la usa para rechazar
peticiones mal formadas (el 422).

**CSV**: archivo de texto donde cada línea es una fila y las columnas van separadas por comas.

**Append-only**: solo se pueden añadir filas al final; nunca se editan ni borran las
anteriores. Es lo que hace fiable un registro de auditoría.

**Persistencia**: que los datos sobrevivan cuando el programa se cierra.

**Delta**: variación de una cantidad. `+30` entra mercadería, `-12` sale.

**Umbral (*threshold*)**: valor límite. Por debajo se considera "stock bajo".

**Slug**: versión de un texto apta para ids: minúsculas, sin acentos, con guiones.

**Race condition**: fallo que ocurre cuando dos operaciones simultáneas se pisan. Se evita con
un *lock*.

**Lock**: candado que deja pasar a una sola operación a la vez.

**ISO 8601**: formato estándar de fechas: `2026-09-24T18:08:13+00:00`.

**UTC**: hora universal, sin zonas horarias ni horario de verano.

**`.env`**: archivo local con secretos y configuración, que **no** se sube al repositorio.

**Variable de entorno**: valor de configuración que lee el programa desde fuera del código.

---

## 2. Diccionarios de Python (`dict`) usados en el proyecto

Un `dict` guarda pares `clave: valor`. Se usan de cuatro maneras distintas:

### a) Tabla de despacho: `TOOL_IMPLEMENTATIONS` (la más importante)

```python
TOOL_IMPLEMENTATIONS = {
    "listar_productos": listar_productos,
    "buscar_producto": buscar_producto,
    "ajustar_stock": ajustar_stock,
    ...
}
```

Aquí las **claves son nombres** (lo que dice el LLM) y los **valores son funciones**. Al
recibir `"ajustar_stock"`, el agente hace `TOOL_IMPLEMENTATIONS["ajustar_stock"](**args)`.

**Por qué un diccionario y no una cadena de `if/elif`:**
- Añadir una tool es añadir **una línea**, no tocar la lógica del bucle.
- Si el LLM inventa una tool que no existe, `.get(name)` devuelve `None` y se maneja con un
  error claro, en lugar de un `KeyError` que rompa el programa.
- Es un patrón muy común llamado *dispatch table*.

### b) Los esquemas de las tools: `TOOL_SCHEMAS` (lista de diccionarios anidados)

Cada tool se describe con un `dict` que sigue el formato exacto que exige la API del LLM. Aquí
no hay elección de diseño: el formato lo impone el proveedor.

### c) Los mensajes del historial

```python
{"role": "user",      "content": "vendimos 12 bolsas de arábica"}
{"role": "assistant", "tool_calls": [...]}
{"role": "tool",      "tool_call_id": "call_1", "content": "{...}"}
```

Tres tipos según quién habla. También es un formato que impone la API.

### d) Las filas del CSV: `csv.DictReader` / `csv.DictWriter`

Cada fila del CSV se lee como un `dict` con las columnas como claves:
`{"id": "cafe-arabica", "name": "Café arábica", "quantity": "40.0", ...}`.

**Por qué `Dict*` y no `csv.reader` normal:** se accede por **nombre de columna**
(`row["quantity"]`) en lugar de por posición (`row[3]`). Si algún día cambias el orden de las
columnas, el código no se rompe.

> Un detalle importante: al leer un CSV, **todos los valores son texto** (`"40.0"`, no `40.0`).
> Por eso `storage.py` convierte con `float(...)` al pasar de fila a `Product`.

### Por qué los datos se sirven como modelos Pydantic y no como `dict` sueltos

Un `dict` acepta cualquier cosa; un modelo Pydantic **exige** que `quantity` sea un número y
que `name` no esté vacío. Los `dict` son cómodos dentro del código; los modelos protegen las
**fronteras** (lo que entra por la API).

---

## 3. Diccionario de datos

### Producto (`data/products.csv`)

| Campo | Tipo | Ejemplo | Significado |
|---|---|---|---|
| `id` | texto | `leche-de-avena` | Identificador único (slug del nombre) |
| `name` | texto | `Leche de avena` | Nombre legible. No puede estar vacío |
| `category` | texto | `Lácteos y alternativas` | Agrupación. Por defecto `general` |
| `quantity` | número decimal | `48.0` | Stock actual. Nunca negativo |
| `unit` | texto | `litros` | Unidad de medida (unidades, kg, litros, bolsas, paquetes...) |
| `min_stock` | número decimal | `12.0` | Umbral propio de stock bajo. Por defecto 5 |
| `updated_at` | texto ISO 8601 | `2026-09-24T17:58:09+00:00` | Última modificación (UTC) |

### Evento del registro (`data/conversation_log.csv`)

| Campo | Ejemplo | Significado |
|---|---|---|
| `actor` | `user` / `assistant` / `tool` | Quién generó el evento |
| `message` | `Listo, se sumaron 30 litros...` | Texto del mensaje o resultado (JSON) de una tool |
| `tool_call` | `{"name": "ajustar_stock", "arguments": {...}}` | Vacío salvo en pedidos y resultados de tools |
| `timestamp` | `2026-09-24T18:08:13+00:00` | Cuándo ocurrió (ISO 8601, UTC) |

Cómo se rellena según el tipo de evento:

| Evento | `actor` | `message` | `tool_call` |
|---|---|---|---|
| El usuario escribe | `user` | el texto | vacío |
| El LLM pide una tool | `assistant` | vacío | JSON con nombre y argumentos |
| Resultado de la tool | `tool` | JSON devuelto por la API | nombre de la tool |
| Respuesta final | `assistant` | el texto | vacío |
