import os, uuid
os.environ.update(DATABASE_URL="sqlite:///./test.db", JWT_SECRET="segredo-de-teste", ADMIN_EMAIL="dono@x.com", ADMIN_PASSWORD="senha-forte-1")
import pytest
from fastapi.testclient import TestClient
from app.main import app

CUST = dict(nome="Maria", sobrenome="Silva", telefone="(87) 98888-7777", cep="55660-000", endereco="Rua A", numero="10", bairro="Centro", cidade="Bezerros", estado="PE")
def order(pid, **k): return {"idem_key": uuid.uuid4().hex, "customer": CUST, "items": [dict(product_id=pid, size="M", qty=2)], "ship": "moto", "pay": "PIX", **k}

@pytest.fixture(scope="module")
def c():
    if os.path.exists("test.db"): os.remove("test.db")
    with TestClient(app) as cl: yield cl

def test_flow(c):
    assert c.get("/api/admin/orders").status_code in (401, 403)  # sem login
    assert c.post("/api/admin/login", json=dict(email="dono@x.com", password="errada")).status_code == 401
    H = {"Authorization": "Bearer " + c.post("/api/admin/login", json=dict(email="dono@x.com", password="senha-forte-1")).json()["token"]}
    assert c.put("/api/admin/settings", headers=H, json=dict(store_name="Mateus Imports", whatsapp="5587900000000", moto_fee=12)).status_code == 200
    cat = c.post("/api/admin/categories", headers=H, json=dict(name="Camisetas")).json()
    p = c.post("/api/admin/products", headers=H, json=dict(name="Camiseta", price=100, promo_price=80, category_id=cat["id"], stock=5, sizes=["P", "M"], images=["data:x"])).json()
    assert c.post("/api/admin/products", headers=H, json=dict(name="Ruim", price=50, promo_price=60)).status_code == 422
    c.post("/api/admin/coupons", headers=H, json=dict(code="bem10", kind="percent", value=10))
    assert c.get("/api/store").json()["products"][0]["images"] == ["data:x"]
    # preço enviado pelo cliente é rejeitado
    assert c.post("/api/orders", json={**order(p["id"]), "total": 1}).status_code == 422
    r = c.post("/api/orders", json=order(p["id"], coupon="BEM10")); assert r.status_code == 201, r.text
    j = r.json(); assert float(j["total"]) == 156.0  # 2x80 - 10% (16) + 12
    assert "wa.me/5587900000000" in j["wa_url"] and "NOVO%20PEDIDO" in j["wa_url"]
    o = order(p["id"], ship="correios"); a = c.post("/api/orders", json=o).json(); b = c.post("/api/orders", json=o).json()
    assert a["number"] == b["number"] and a["total"] is None and a["shipping_pending"]  # sem duplicar; frete pendente
    assert c.get("/api/admin/products", headers=H).json()[0]["stock"] == 1  # 5 - 2 - 2
    assert c.post("/api/orders", json=order(p["id"])).status_code == 400  # estoque insuficiente
    assert c.post("/api/orders", json={**order(p["id"]), "items": [dict(product_id=p["id"], qty=1)]}).status_code == 400  # sem variação
    n = j["number"]; assert c.patch(f"/api/admin/orders/{n}", headers=H, json=dict(status="Cancelado")).status_code == 200
    assert c.get("/api/admin/products", headers=H).json()[0]["stock"] == 3  # estoque devolvido
    c.patch(f"/api/admin/orders/{a['number']}", headers=H, json=dict(shipping=20)); assert float(c.get(f"/api/admin/orders/{a['number']}", headers=H).json()["total"]) == 180.0
    c.patch(f"/api/admin/orders/{a['number']}", headers=H, json=dict(status="Concluído"))
    d = c.get("/api/admin/dashboard", headers=H).json(); assert float(d["month"]) == 180.0 and d["orders"] == 2 and d["completed"] == 1  # cancelado fora
    assert c.delete(f"/api/admin/categories/{cat['id']}", headers=H).status_code == 409
