from api import storage


def buscar(client, texto):
    return [p["id"] for p in client.get("/products/search", params={"q": texto}).json()]


def test_inventario_inicial_tiene_diez_productos(client):
    r = client.get("/inventory")
    assert r.status_code == 200
    assert len(r.json()) == 10


def test_crear_producto_devuelve_201_y_aparece_en_listado(client):
    r = client.post("/inventory", json={"name": "Té chai", "quantity": 4, "unit": "kg"})
    assert r.status_code == 201
    assert r.json()["id"] == "te-chai"
    assert any(p["id"] == "te-chai" for p in client.get("/inventory").json())


def test_crear_producto_duplicado_devuelve_409(client):
    r = client.post("/inventory", json={"name": "Café arábica", "quantity": 1, "unit": "kg"})
    assert r.status_code == 409
    assert "ya existe" in r.json()["detail"]


def test_crear_producto_invalido_devuelve_422(client):
    assert client.post("/inventory", json={"name": "X", "quantity": -5, "unit": "kg"}).status_code == 422
    assert client.post("/inventory", json={"name": "", "quantity": 5, "unit": "kg"}).status_code == 422
    assert client.post("/inventory", json={"name": "X", "quantity": 5}).status_code == 422


def test_ajuste_positivo_y_negativo(client):
    r = client.patch("/inventory/leche-de-avena", json={"delta": 30})
    assert r.status_code == 200 and r.json()["quantity"] == 48
    r = client.patch("/inventory/leche-de-avena", json={"delta": -8})
    assert r.json()["quantity"] == 40


def test_ajuste_producto_inexistente_devuelve_404_con_mensaje_limpio(client):
    r = client.patch("/inventory/no-existe", json={"delta": 1})
    assert r.status_code == 404
    assert r.json()["detail"] == "Producto 'no-existe' no encontrado"


def test_stock_insuficiente_devuelve_400_y_no_modifica_el_stock(client):
    r = client.patch("/inventory/cafe-arabica", json={"delta": -999})
    assert r.status_code == 400
    assert "Stock insuficiente" in r.json()["detail"]
    assert client.get("/products/cafe-arabica").json()["quantity"] == 40


def test_alertas_por_defecto_usan_umbral_10(client):
    nombres = [p["id"] for p in client.get("/inventory/alerts").json()]
    assert nombres == ["cacao-en-polvo"]


def test_alertas_con_umbral_configurable(client):
    ids = [p["id"] for p in client.get("/inventory/alerts", params={"threshold": 20}).json()]
    assert {"cacao-en-polvo", "leche-de-avena", "servilletas", "bolsas-de-arabica-1kg"} <= set(ids)


def test_alertas_umbral_negativo_devuelve_422(client):
    assert client.get("/inventory/alerts", params={"threshold": -1}).status_code == 422


def test_low_stock_usa_el_minimo_de_cada_producto(client):
    client.patch("/inventory/servilletas", json={"delta": -6})  # 15 -> 9, minimo 10
    assert "servilletas" in [p["id"] for p in client.get("/products/low-stock").json()]


def test_busqueda_ignora_acentos_y_mayusculas(client):
    assert "cafe-arabica" in buscar(client, "ARABICA")


def test_busqueda_tolera_erratas(client):
    assert "cafe-arabica" in buscar(client, "árbica")
    assert buscar(client, "lechee de avena") == ["leche-de-avena"]


def test_busqueda_sin_resultados_devuelve_lista_vacia(client):
    r = client.get("/products/search", params={"q": "zzzzz"})
    assert r.status_code == 200 and r.json() == []


def test_busqueda_sin_parametro_devuelve_422(client):
    assert client.get("/products/search").status_code == 422


def test_raiz_redirige_a_docs(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/docs"


def test_los_datos_persisten_en_el_csv(client):
    client.post("/inventory", json={"name": "Miel", "quantity": 8, "unit": "kg"})
    assert "Miel" in storage.CSV_PATH.read_text(encoding="utf-8")
    assert any(p.id == "miel" for p in storage.list_products())


def test_con_api_key_definida_se_exige_la_cabecera(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "secreta")
    assert client.get("/inventory").status_code == 401
    assert client.get("/inventory", headers={"X-API-Key": "mala"}).status_code == 401
    assert client.get("/inventory", headers={"X-API-Key": "secreta"}).status_code == 200
    assert client.patch("/inventory/servilletas", json={"delta": 1}).status_code == 401


def test_health_y_docs_siguen_abiertos_con_api_key(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "secreta")
    assert client.get("/health").status_code == 200
    assert client.get("/docs").status_code == 200
