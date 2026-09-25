import copy
import inspect
import json

import pytest
import urllib.error
from jsonschema import Draft202012Validator

import agent
from agent_lib import tools
from agent_lib.logger import log_event  # noqa: F401  (asegura que el módulo esté cargado)


class Fn:
    def __init__(self, name, args):
        self.name, self.arguments = name, json.dumps(args)


class ToolCall:
    def __init__(self, id, name, args):
        self.id, self.function = id, Fn(name, args)


class Msg:
    def __init__(self, content=None, tool_calls=None):
        self.content, self.tool_calls = content, tool_calls

    def model_dump(self, exclude_none=True):
        d = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [
                {"id": t.id, "type": "function", "function": {"name": t.function.name, "arguments": t.function.arguments}}
                for t in self.tool_calls
            ]
        return {k: v for k, v in d.items() if v is not None}


class FakeClient:
    """LLM simulado: devuelve los mensajes del guion y guarda una foto del historial recibido en cada llamada."""

    def __init__(self, guion):
        self.guion, self.vistos = list(guion), []
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.vistos.append(copy.deepcopy(kwargs["messages"]))
        msg = self.guion[len(self.vistos) - 1]
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()


@pytest.fixture
def api_via_testclient(client, monkeypatch):
    """Redirige el transporte HTTP de las tools hacia la API en memoria (TestClient)."""
    llamadas = []

    def falso(method, url, headers, data):
        ruta = "/" + url.split("://", 1)[1].split("/", 1)[1]
        llamadas.append((method, ruta.split("?", 1)[0]))
        r = client.request(method, ruta, content=data, headers=headers)
        return r.status_code, r.text

    monkeypatch.setattr(tools, "_send", falso)
    return llamadas


def historial(texto):
    return [{"role": "system", "content": "sp"}, {"role": "user", "content": texto}]


def test_termina_en_la_primera_llamada_si_no_hay_tool_calls(api_via_testclient):
    cliente = FakeClient([Msg(content="Hola")])
    assert agent.run_turn(cliente, historial("hola")) == "Hola"
    assert len(cliente.vistos) == 1


def test_varios_pasos_y_el_resultado_entra_al_historial_antes_de_la_siguiente_iteracion(api_via_testclient, client):
    cliente = FakeClient([
        Msg(tool_calls=[ToolCall("c1", "buscar_producto", {"consulta": "avena"})]),
        Msg(tool_calls=[ToolCall("c2", "ajustar_stock", {"producto_id": "leche-de-avena", "delta": 30})]),
        Msg(content="Listo"),
    ])
    assert agent.run_turn(cliente, historial("llegaron 30 de avena")) == "Listo"
    assert [len(h) for h in cliente.vistos] == [2, 4, 6]
    ultimo = cliente.vistos[2]
    assert ultimo[3]["role"] == "tool" and ultimo[3]["tool_call_id"] == "c1"
    assert ultimo[5]["role"] == "tool" and ultimo[5]["tool_call_id"] == "c2"
    assert client.get("/products/leche-de-avena").json()["quantity"] == 48
    assert not any('"error"' in m["content"] for m in ultimo if m["role"] == "tool")


def test_crear_y_luego_consultar_alertas_en_el_mismo_turno(api_via_testclient):
    cliente = FakeClient([
        Msg(tool_calls=[ToolCall("c1", "crear_producto", {"nombre": "Miel", "cantidad": 2, "unidad": "kg"})]),
        Msg(tool_calls=[ToolCall("c2", "productos_bajo_stock", {})]),
        Msg(content="ok"),
    ])
    agent.run_turn(cliente, historial("agrega miel y dime alertas"))
    resultado_alertas = json.loads(cliente.vistos[2][-1]["content"])
    assert "error" not in resultado_alertas
    assert "Miel" in [p["name"] for p in resultado_alertas["productos_bajo_stock"]]


def test_corta_por_el_tope_de_iteraciones(api_via_testclient):
    bucle = [Msg(tool_calls=[ToolCall(f"c{i}", "listar_productos", {})]) for i in range(agent.MAX_TOOL_ITERATIONS)]
    cliente = FakeClient(bucle)
    respuesta = agent.run_turn(cliente, historial("x"))
    assert len(cliente.vistos) == agent.MAX_TOOL_ITERATIONS
    assert "reformular" in respuesta


def test_tool_desconocida_se_devuelve_como_error_sin_romper_el_bucle(api_via_testclient):
    cliente = FakeClient([Msg(tool_calls=[ToolCall("c1", "inventada", {})]), Msg(content="no puedo")])
    assert agent.run_turn(cliente, historial("x")) == "no puedo"
    assert json.loads(cliente.vistos[1][-1]["content"])["error"] is True


def test_api_caida_no_rompe_el_agente(monkeypatch):
    def caida(*a, **k):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(tools, "_send", caida)
    cliente = FakeClient([Msg(tool_calls=[ToolCall("c1", "listar_productos", {})]), Msg(content="La API está caída")])
    assert agent.run_turn(cliente, historial("x")) == "La API está caída"
    assert "Connection refused" in cliente.vistos[1][-1]["content"]


def test_cada_tool_llama_al_endpoint_correcto(api_via_testclient):
    casos = [
        ("listar_productos", {}, ("GET", "/inventory")),
        ("buscar_producto", {"consulta": "avena"}, ("GET", "/products/search")),
        ("productos_bajo_stock", {"umbral": 20}, ("GET", "/inventory/alerts")),
        ("crear_producto", {"nombre": "Miel", "cantidad": 5, "unidad": "kg"}, ("POST", "/inventory")),
        ("ajustar_stock", {"producto_id": "cafe-arabica", "delta": -3}, ("PATCH", "/inventory/cafe-arabica")),
    ]
    for nombre, args, esperado in casos:
        resultado = tools.TOOL_IMPLEMENTATIONS[nombre](**args)
        assert api_via_testclient[-1] == esperado
        assert "error" not in resultado


def test_el_agente_envia_la_api_key_si_esta_definida(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "secreta")
    recibido = {}

    def falso(method, url, headers, data):
        recibido.update(headers)
        r = client.request(method, "/inventory", headers=headers)
        return r.status_code, r.text

    monkeypatch.setattr(tools, "_send", falso)
    assert isinstance(tools.listar_productos()["productos"], list)
    assert recibido["X-API-Key"] == "secreta"


def test_error_de_la_api_llega_al_llm_como_dato_con_codigo_y_detalle(api_via_testclient):
    r = tools.ajustar_stock("cafe-arabica", -999)
    assert r["error"] is True and r["status_code"] == 400 and "Stock insuficiente" in r["detail"]


def test_los_eventos_del_turno_quedan_en_el_log(api_via_testclient):
    import agent_lib.logger as lg

    cliente = FakeClient([Msg(tool_calls=[ToolCall("c1", "listar_productos", {})]), Msg(content="fin")])
    agent.run_turn(cliente, historial("x"))
    actores = [r.split(",", 1)[0] for r in lg.LOG_PATH.read_text(encoding="utf-8").splitlines()[1:]]
    assert actores == ["assistant", "tool", "assistant"]


@pytest.mark.parametrize("schema", tools.TOOL_SCHEMAS, ids=lambda s: s["function"]["name"])
def test_esquemas_validos_y_coinciden_con_las_funciones(schema):
    f = schema["function"]
    assert f["name"] and f["description"]
    Draft202012Validator.check_schema(f["parameters"])
    firma = set(inspect.signature(tools.TOOL_IMPLEMENTATIONS[f["name"]]).parameters)
    assert set(f["parameters"]["properties"]) == firma
    assert set(f["parameters"]["required"]) <= firma


def _error_400(mensaje):
    import httpx
    from openai import BadRequestError

    respuesta = httpx.Response(400, request=httpx.Request("POST", "http://groq.test"))
    return BadRequestError(mensaje, response=respuesta, body=None)


class ClienteQueFallaAntes(FakeClient):
    def __init__(self, guion, fallos, mensaje):
        super().__init__(guion)
        self.fallos, self.mensaje, self.llamadas = fallos, mensaje, 0

    def create(self, **kwargs):
        self.llamadas += 1
        if self.llamadas <= self.fallos:
            raise _error_400(self.mensaje)
        return super().create(**kwargs)


ERROR_TOOL = "Tool call validation failed: attempted to call tool 'buscar_producto<|channel|>commentary'"


def test_reintenta_cuando_el_modelo_escribe_mal_el_nombre_de_una_tool(api_via_testclient):
    cliente = ClienteQueFallaAntes([Msg(content="ok")], fallos=2, mensaje=ERROR_TOOL)
    assert agent.run_turn(cliente, historial("x")) == "ok"
    assert cliente.llamadas == 3


def test_se_rinde_tras_los_reintentos_maximos(api_via_testclient):
    from openai import BadRequestError

    cliente = ClienteQueFallaAntes([Msg(content="ok")], fallos=99, mensaje=ERROR_TOOL)
    with pytest.raises(BadRequestError):
        agent.run_turn(cliente, historial("x"))
    assert cliente.llamadas == agent.MAX_REINTENTOS_LLM


def test_no_reintenta_otros_errores_400(api_via_testclient):
    from openai import BadRequestError

    cliente = ClienteQueFallaAntes([Msg(content="ok")], fallos=99, mensaje="model_not_found")
    with pytest.raises(BadRequestError):
        agent.run_turn(cliente, historial("x"))
    assert cliente.llamadas == 1
