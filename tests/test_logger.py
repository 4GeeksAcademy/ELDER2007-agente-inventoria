import csv
from datetime import datetime

import agent_lib.logger as logger


def leer():
    with logger.LOG_PATH.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_se_crea_con_los_cuatro_campos():
    logger.log_event(actor="user", message="hola")
    with logger.LOG_PATH.open(encoding="utf-8") as f:
        assert f.readline().strip() == "actor,message,tool_call,timestamp"


def test_cada_evento_tiene_los_cuatro_campos_y_timestamp_iso():
    logger.log_event(actor="user", message="hola")
    logger.log_event(actor="assistant", tool_call={"name": "listar_productos", "arguments": {}})
    logger.log_event(actor="tool", message="{}", tool_call="listar_productos")
    filas = leer()
    assert len(filas) == 3
    for fila in filas:
        assert set(fila) == {"actor", "message", "tool_call", "timestamp"}
        assert datetime.fromisoformat(fila["timestamp"]).tzinfo is not None
    assert '"name": "listar_productos"' in filas[1]["tool_call"]


def test_solo_adicion_entre_sesiones():
    logger.log_event(actor="user", message="sesion 1")
    antes = logger.LOG_PATH.read_bytes()
    logger.log_event(actor="user", message="sesion 2")
    despues = logger.LOG_PATH.read_bytes()
    assert despues.startswith(antes)
    assert despues.count(b"actor,message,tool_call,timestamp") == 1
    assert [f["message"] for f in leer()] == ["sesion 1", "sesion 2"]
