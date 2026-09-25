# 3. El bucle del agente

Un **agente** es, en esencia, un LLM dentro de un bucle que puede ejecutar acciones y ver su
resultado. Todo lo demás es detalle. Este proyecto lo implementa en [`agent.py`](../agent.py)
con funciones simples.

## Las cinco fases

| Fase | Función | Qué hace |
|---|---|---|
| **Observar** | `observar()` | Lee lo que escribe el usuario en la terminal |
| **Pensar** | `pensar(client, history)` | Manda al LLM el historial + las tools; el LLM decide |
| **Actuar** | `actuar(tool_call)` | Ejecuta la tool elegida haciendo un pedido HTTP a la API |
| **Actualizar** | `actualizar_con_decision()` y `actualizar_con_resultado()` | Añade al historial lo que dijo el LLM y lo que devolvió la tool |
| **Repetir** | `run_turn()` | Vuelve a *pensar* con el historial ya actualizado |

## El código esencial (simplificado)

```python
def run_turn(client, history):
    for _ in range(MAX_TOOL_ITERATIONS):            # tope de seguridad
        message = pensar(client, history)            # PENSAR
        actualizar_con_decision(history, message)    # ACTUALIZAR

        if not message.tool_calls:                   # ¿el LLM ya no pide tools?
            return message.content                   #  → respuesta final, se acaba

        for tool_call in message.tool_calls:
            resultado = actuar(tool_call)            # ACTUAR
            actualizar_con_resultado(history, tool_call, resultado)   # ACTUALIZAR
        # REPETIR: el for vuelve arriba y el LLM ve el resultado
```

## Cuándo termina el bucle

Hay **dos** salidas:

1. **La normal:** el LLM responde con texto y sin `tool_calls`. Se devuelve y el bucle corta.
   Es la condición `if not message.tool_calls`.
2. **La de seguridad:** se llegó a 8 vueltas sin respuesta final. Se devuelve un mensaje de
   disculpa. Sirve para que un fallo del modelo no genere un ciclo infinito.

## Un turno real, tal como quedó en el log

Frase del usuario: *"llegaron 30 unidades de leche de avena"*

```
user       llegaron 30 unidades de leche de avena
assistant  {"name": "buscar_producto", "arguments": {"consulta": "leche de avena"}}   ← vuelta 1: pensar
tool       buscar_producto                                                              ← actuar
assistant  {"name": "ajustar_stock", "arguments": {"delta": 30, "producto_id": ...}}   ← vuelta 2: pensar
tool       ajustar_stock                                                                ← actuar
assistant  Listo, se sumaron 30 litros a Leche de avena. Ahora tienes 48 litros...      ← respuesta final
```

Fíjate: **dos vueltas** de pensar→actuar antes de la respuesta final. Con la pregunta
"¿qué productos están por agotarse?" bastó una sola. El número de vueltas lo decide el LLM.

## Por qué el historial crece así

En cada vuelta el LLM recibe **todo** el historial. Se comprobó que crece de dos en dos
mensajes (el pedido del LLM y el resultado de la tool):

| Iteración | Mensajes que ve el LLM |
|---|---|
| 1 | 2 (sistema + usuario) |
| 2 | 4 (+ su pedido de tool + el resultado) |
| 3 | 6 (+ otro pedido + otro resultado) |

El LLM **no tiene memoria propia**: solo "recuerda" lo que le reenvías en cada llamada. Por eso
el historial es tan importante, y por eso cada resultado lleva un `tool_call_id`: es la
etiqueta que le dice al modelo a qué pedido suyo corresponde cada respuesta.

## Cómo se define una tool

Cada tool son **dos cosas** en [`agent_lib/tools.py`](../agent_lib/tools.py):

1. **Un esquema** (para el LLM): `name`, `description` y `parameters` en JSON Schema.
2. **Una función Python** (para ti): la que hace el pedido HTTP.

Se unen con un diccionario `{nombre: función}` (ver [04-diccionario.md](04-diccionario.md)).

```python
# 1. El esquema: lo que el LLM lee para decidir
{"type": "function", "function": {
    "name": "ajustar_stock",
    "description": "Suma o resta una cantidad al stock de un producto existente...",
    "parameters": {"type": "object",
        "properties": {"producto_id": {"type": "string"}, "delta": {"type": "number"}, ...},
        "required": ["producto_id", "delta"]}}}

# 2. La función: lo que se ejecuta de verdad
def ajustar_stock(producto_id, delta, motivo=None):
    return _request("PATCH", f"/inventory/{producto_id}", json={"delta": delta, "reason": motivo})
```

**La `description` es lo más importante.** Es el único "manual" que tiene el LLM. Una
descripción vaga produce llamadas equivocadas; por eso las de este proyecto dicen *cuándo*
usar cada tool y en qué orden (por ejemplo, "úsala SIEMPRE antes de ajustar stock").

## Cómo se comprobó que funciona

- Las llamadas reales del LLM se validaron contra los esquemas con `jsonschema` (5 de 5
  válidas).
- Se interceptaron los pedidos HTTP para confirmar que cada tool llega al endpoint correcto.
- Se fotografió el historial en cada iteración para confirmar que el resultado entra antes
  de la siguiente llamada.
- Se ejecutó todo con Groq de verdad y el stock cambió en la API.
