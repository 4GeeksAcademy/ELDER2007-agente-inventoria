"""Agente de inventario conversacional.

Implementa el ciclo clásico de un agente con tools, explícito paso a paso:

    OBSERVAR   -> se recibe el mensaje del usuario en lenguaje natural
    PENSAR     -> se le pasa el historial completo + las tools al LLM
    ACTUAR     -> si el LLM pidió una tool, se ejecuta contra la API REST
    ACTUALIZAR -> el resultado se agrega al historial en memoria
    REPETIR    -> se vuelve a pensar con el historial actualizado, hasta que
                  el LLM responde sin pedir más tools (respuesta final)

Todo el historial vive en memoria durante la sesión. Cada evento (mensaje del
usuario, llamada a tool, resultado, respuesta final) se registra además en
data/conversation_log.csv, que es append-only y sobrevive a reinicios del
agente.

Arranque (con la API ya corriendo en otra terminal):
    python agent.py
"""
import json
import os
import sys

from dotenv import load_dotenv
from openai import BadRequestError, OpenAI

from agent_lib.logger import log_event
from agent_lib.tools import TOOL_IMPLEMENTATIONS, TOOL_SCHEMAS

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
MAX_TOOL_ITERATIONS = 8  # tope de vueltas pensar/actuar/actualizar por turno, evita loops infinitos
MAX_REINTENTOS_LLM = 3  # el modelo a veces escribe mal el nombre de una tool y Groq responde 400

SYSTEM_PROMPT = """Eres el asistente de inventario de una tienda. Hablás español, en tono \
cercano y directo, como si le respondieras a la persona que administra el local.

Tenés acceso a herramientas que consultan y modifican el inventario real (que vive en un CSV \
detrás de una API). Nunca inventes cantidades ni productos: usá siempre las herramientas para \
leer o modificar datos.

Reglas importantes:
- Antes de ajustar stock o crear un producto, usá 'buscar_producto' para encontrar su id exacto \
o confirmar que no existe.
- Si el mensaje dice que "llegaron", "entraron" o "se recibieron" unidades, ajustá el stock con \
un delta POSITIVO.
- Si el mensaje dice que se "vendieron", "salieron" o se "usaron" unidades, ajustá el stock con \
un delta NEGATIVO.
- Si el producto mencionado no existe todavía y por el contexto es claramente un alta nueva \
(por ejemplo "agregá X al inventario"), creálo con 'crear_producto'. Si es ambiguo, preguntá \
antes de inventar datos.
- Cuando te pregunten qué está por agotarse o similar, usá 'productos_bajo_stock'. Si te dan un \
número explícito (p. ej. "por debajo de 20"), pasalo como 'umbral'; si no, dejalo vacío y la API \
usa 10 por defecto.
- Si 'ajustar_stock' devuelve un error de stock insuficiente, no lo reintentes con otro número \
inventado: explicale a la persona cuánto hay disponible y preguntá cómo seguir.
- Respondé siempre de forma breve y conversacional, confirmando qué se actualizó (producto, \
cantidad nueva, unidad) o la información pedida. Si un producto quedó en o por debajo de su \
umbral mínimo después de un ajuste, avisalo.
- Si dicen que "llegaron" o "vendieron" un producto que NO existe en el inventario, no lo \
crees por tu cuenta: preguntá si quieren darlo de alta (con qué unidad) antes de hacerlo.
- Solo podés gestionar este inventario con las herramientas que tenés. No podés cambiar la \
categoría ni el stock mínimo de un producto ya creado, ni borrar productos, ni enviar avisos \
o notificaciones por tu cuenta (solo informás cuando te preguntan). Si te piden algo así, o \
algo ajeno al inventario (el clima, noticias), decí claramente que no podés; no lo prometas ni \
ofrezcas hacerlo.
"""


def _print_banner():
    print("=" * 60)
    print(" Agente de Inventario — escribí en lenguaje natural")
    print(' Ej: "llegaron 30 litros de leche de avena"')
    print(' Ej: "vendimos 12 bolsas de arábica"')
    print(' Ej: "¿qué productos están por agotarse?"')
    print(' Salí con Ctrl+C')
    print("=" * 60)


# --------------------------------------------------------------------------
# OBSERVAR
# --------------------------------------------------------------------------
def observar() -> str:
    """Recibe el mensaje del usuario en lenguaje natural desde la terminal."""
    return input("\nVos: ").strip()


# --------------------------------------------------------------------------
# PENSAR
# --------------------------------------------------------------------------
def pensar(client: OpenAI, history: list):
    """Le pasa al LLM todo el historial de la sesión junto con las tools disponibles.

    El LLM decide, en base a ese historial, si responde directamente o si pide
    ejecutar una o más tools antes de poder responder.
    """
    for intento in range(1, MAX_REINTENTOS_LLM + 1):
        try:
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=history,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
            )
            return response.choices[0].message
        except BadRequestError as exc:
            # Fallo puntual del modelo (tool inexistente/mal escrita): reintentar suele bastar.
            if "tool call validation failed" not in str(exc).lower() or intento == MAX_REINTENTOS_LLM:
                raise


# --------------------------------------------------------------------------
# ACTUAR
# --------------------------------------------------------------------------
def actuar(tool_call) -> str:
    """Ejecuta la tool que pidió el LLM llamando al endpoint real de la API."""
    name = tool_call.function.name
    try:
        args = json.loads(tool_call.function.arguments or "{}")
    except json.JSONDecodeError:
        args = {}

    log_event(actor="assistant", tool_call={"name": name, "arguments": args})

    implementation = TOOL_IMPLEMENTATIONS.get(name)
    if implementation is None:
        result = {"error": True, "detail": f"Tool desconocida: {name}"}
    else:
        try:
            result = implementation(**args)
        except Exception as exc:  # la API/red pueden fallar; se lo devolvemos al LLM
            result = {"error": True, "detail": str(exc)}

    result_json = json.dumps(result, ensure_ascii=False)
    log_event(actor="tool", message=result_json, tool_call=name)
    return result_json


# --------------------------------------------------------------------------
# ACTUALIZAR
# --------------------------------------------------------------------------
def actualizar_con_decision(history: list, message) -> None:
    """Agrega al historial en memoria la decisión del LLM (respuesta o pedido de tools)."""
    history.append(message.model_dump(exclude_none=True))


def actualizar_con_resultado(history: list, tool_call, result_json: str) -> None:
    """Agrega al historial en memoria el resultado de haber actuado una tool."""
    history.append(
        {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result_json,
        }
    )


def run_turn(client: OpenAI, history: list) -> str:
    """Ciclo Pensar -> Actuar -> Actualizar -> Repetir, hasta obtener una respuesta final."""
    for _ in range(MAX_TOOL_ITERATIONS):
        message = pensar(client, history)
        actualizar_con_decision(history, message)

        if not message.tool_calls:
            log_event(actor="assistant", message=message.content or "")
            return message.content or ""

        for tool_call in message.tool_calls:
            result_json = actuar(tool_call)
            actualizar_con_resultado(history, tool_call, result_json)
        # REPETIR: se vuelve al inicio del for a pensar con el historial ya actualizado

    fallback = "Che, me enredé con varias herramientas seguidas. ¿Podés reformular el pedido?"
    log_event(actor="assistant", message=fallback)
    return fallback


def main():
    if not GROQ_API_KEY:
        print("Falta GROQ_API_KEY. Creá un archivo .env con GROQ_API_KEY=tu_clave y volvé a intentar.")
        sys.exit(1)

    client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
    history = [{"role": "system", "content": SYSTEM_PROMPT}]

    _print_banner()

    while True:
        try:
            user_input = observar()
        except (KeyboardInterrupt, EOFError):
            print("\nHasta luego. El inventario quedó guardado en el CSV.")
            break

        if not user_input:
            continue

        log_event(actor="user", message=user_input)
        history.append({"role": "user", "content": user_input})

        try:
            reply = run_turn(client, history)
        except Exception as exc:
            reply = f"Tuve un problema hablando con la API o el modelo: {exc}"
            log_event(actor="assistant", message=reply)

        print(f"Agente: {reply}")


if __name__ == "__main__":
    main()
