import os, datetime as dt
from contextlib import asynccontextmanager
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional
from urllib.parse import quote
import bcrypt, jwt
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .models import *
from .seed import seed_if_empty
from .backup import make_backup, snap, start_scheduler

SECRET = os.environ["JWT_SECRET"]  # obrigatório
STATUS = ["Aguardando confirmação", "Pedido confirmado", "Em preparação", "Saiu para entrega", "Disponível para retirada", "Concluído", "Cancelado"]
D = lambda x: Decimal(str(x)).quantize(Decimal("0.01"), ROUND_HALF_UP)

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.get(Setting, 1): db.add(Setting(id=1))
        e, p = os.getenv("ADMIN_EMAIL"), os.getenv("ADMIN_PASSWORD")
        if e and p and not db.scalar(select(Admin)):
            db.add(Admin(email=e.lower(), password_hash=bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()))
        db.commit()
        if os.getenv("AUTO_SEED", "1") != "0": print(f"Catálogo inicial: {seed_if_empty(db)} produtos importados" if not db.query(Product).count() else "Catálogo já existe no banco")
        if os.getenv("BACKUP", "1") != "0":  # cópia ao iniciar e a cada 6 horas
            try: print("Backup:", make_backup())
            except Exception as e: print("Falha no backup:", e)
            start_scheduler()
    yield

app = FastAPI(title="Mateus Imports API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o], allow_methods=["*"], allow_headers=["*"])

# ---------- schemas ----------
class Strict(BaseModel): model_config = ConfigDict(extra="forbid")
class CustomerIn(Strict):
    nome: str = Field(min_length=1, max_length=80); sobrenome: str = Field(min_length=1, max_length=80)
    telefone: str; cep: str; endereco: str = Field(min_length=1); numero: str = Field(min_length=1)
    complemento: str = ""; bairro: str = Field(min_length=1); cidade: str = Field(min_length=1); estado: str = Field(min_length=2, max_length=2); referencia: str = ""
    @field_validator("telefone")
    def _t(cls, v):
        if len("".join(c for c in v if c.isdigit())) < 10: raise ValueError("Celular inválido (use DDD)")
        return v
    @field_validator("cep")
    def _c(cls, v):
        if len("".join(c for c in v if c.isdigit())) != 8: raise ValueError("CEP inválido")
        return v
class ItemIn(Strict): product_id: int; size: str = ""; color: str = ""; qty: int = Field(ge=1, le=99)
class OrderIn(Strict):  # o cliente NUNCA envia preços
    idem_key: str = Field(min_length=8, max_length=80); customer: CustomerIn; items: list[ItemIn] = Field(min_length=1, max_length=50)
    ship: Literal["pickup", "moto", "correios", "transportadora"]; cep: str = ""
    pay: Literal["PIX", "Cartão de débito", "Cartão de crédito", "Dinheiro", "Outros"]; pay_note: str = ""; notes: str = ""; coupon: str = ""
class CategoryIn(Strict): name: str = Field(min_length=1); description: str = ""; image: str = ""; sort_order: int = 0; active: bool = True
class ProductIn(Strict):
    name: str = Field(min_length=1); description: str = ""; price: Decimal = Field(gt=0); promo_price: Optional[Decimal] = Field(default=None, gt=0)
    category_id: Optional[int] = None; stock: int = Field(ge=0, default=0); sizes: list[str] = []; colors: list[str] = []; active: bool = True; images: Optional[list[str]] = None
class CouponIn(Strict):
    code: str = Field(min_length=1); kind: Literal["percent", "fixed"]; value: Decimal = Field(gt=0); expires_on: Optional[dt.date] = None
    max_uses: Optional[int] = Field(default=None, ge=1); min_purchase: Decimal = Field(default=Decimal(0), ge=0); active: bool = True
class SettingsIn(Strict):
    store_name: str; whatsapp: str; address: str = ""; hours: str = ""; moto_fee: Decimal = Field(ge=0); pix_key: str = ""; pay_info: str = ""
    pickup_info: str = ""; socials: str = ""; logo_url: str = ""; banner_url: str = ""
class OrderPatch(Strict):
    status: Optional[Literal[tuple(STATUS)]] = None; internal_note: Optional[str] = None; shipping: Optional[Decimal] = Field(default=None, ge=0)
class LoginIn(Strict): email: str; password: str

# ---------- pedido: tudo calculado no servidor ----------
def build(db: Session, o: OrderIn, lock: bool):
    st = db.get(Setting, 1); lines, sub, used = [], D(0), {}
    for it in o.items:
        q = select(Product).where(Product.id == it.product_id, Product.active == True)
        p = db.scalar(q.with_for_update() if lock else q)
        if not p: raise HTTPException(400, "Produto indisponível")
        used[p.id] = used.get(p.id, 0) + it.qty
        if p.stock < used[p.id]: raise HTTPException(400, f"Estoque insuficiente: {p.name}")
        if (p.sizes and it.size not in p.sizes) or (p.colors and it.color not in p.colors): raise HTTPException(400, f"Selecione as variações de {p.name}")
        u = D(p.promo_price if p.promo_price and p.promo_price < p.price else p.price)
        lines.append((p, it, u, u * it.qty)); sub += u * it.qty
    disc, cp, code = D(0), None, o.coupon.strip().upper()
    if code:
        q = select(Coupon).where(Coupon.code == code)
        cp = db.scalar(q.with_for_update() if lock else q)
        if not cp or not cp.active or (cp.expires_on and cp.expires_on < dt.date.today()) or (cp.max_uses and cp.used_count >= cp.max_uses) or sub < cp.min_purchase:
            raise HTTPException(400, "Cupom inválido")
        disc = min(sub, D(sub * cp.value / 100) if cp.kind == "percent" else D(cp.value))
    ship = {"pickup": D(0), "moto": D(st.moto_fee)}.get(o.ship)  # correios/transportadora -> None (a confirmar)
    return st, lines, sub, disc, cp, ship, (None if ship is None else max(D(0), sub + ship - disc))

@app.post("/api/quote")
def quote_order(o: OrderIn, db: Session = Depends(get_db)):
    _, lines, sub, disc, _, ship, total = build(db, o, False)
    return dict(subtotal=sub, discount=disc, shipping=ship, total=total, shipping_pending=ship is None)

R = lambda n: f"R$ {D(n):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
SHIPN = {"pickup": "Retirada na loja", "moto": "99Moto", "correios": "Correios", "transportadora": "Transportadora"}
def wa_url(od: Order, st: Setting, o: OrderIn):
    c = o.customer
    items = "\n\n".join(f"Nome do produto: {i.name}\nVariação: {i.variation or '-'}\nQuantidade: {i.qty}\nPreço unitário: {R(i.unit_price)}\nSubtotal: {R(i.subtotal)}" for i in od.items)
    tot = R(od.total) if od.total is not None else f"{R(od.subtotal - od.discount)} + frete a confirmar"
    m = (f"*NOVO PEDIDO — {st.store_name.upper()}*\n\nNúmero do pedido: #{od.id:06d}\n\n*DADOS DO CLIENTE:*\nNome completo: {c.nome} {c.sobrenome}\nTelefone: {c.telefone}\n"
         f"Endereço: {c.endereco}, {c.numero} {c.complemento} - {c.bairro}, {c.cidade}/{c.estado}\nCEP: {c.cep}\n\n*PRODUTOS:*\n{items}\n\n*RESUMO:*\nSubtotal: {R(od.subtotal)}\n"
         f"Desconto: {R(od.discount)}\nCupom: {od.coupon_code or '-'}\nEntrega: {SHIPN[od.ship_method]}\nValor da entrega: {'a confirmar' if od.shipping is None else R(od.shipping)}\n"
         f"Forma de pagamento: {od.pay_method}\n*TOTAL: {tot}*\n\n*OBSERVAÇÕES:*\n{' | '.join(x for x in (o.pay_note, o.notes) if x) or '-'}")
    return "https://wa.me/" + "".join(ch for ch in st.whatsapp if ch.isdigit()) + "?text=" + quote(m)

def _create_order(o: OrderIn, db: Session):
    st = db.get(Setting, 1)
    if not "".join(ch for ch in st.whatsapp if ch.isdigit()): raise HTTPException(503, "WhatsApp da loja não configurado")
    def done(od): return dict(number=od.id, status=od.status, total=od.total, shipping_pending=od.shipping is None, wa_url=wa_url(od, st, o))
    if ex := db.scalar(select(Order).where(Order.idem_key == o.idem_key)): return done(ex)  # clique repetido
    try:
        st, lines, sub, disc, cp, ship, total = build(db, o, True)
        c = o.customer; cu = Customer(first_name=c.nome, last_name=c.sobrenome, phone=c.telefone); db.add(cu); db.flush()
        od = Order(idem_key=o.idem_key, customer_id=cu.id, customer=c.model_dump(), ship_method=o.ship, cep=o.cep or c.cep, pay_method=o.pay, pay_note=o.pay_note, notes=o.notes,
                   coupon_code=cp.code if cp else "", subtotal=sub, discount=disc, shipping=ship, total=total)
        for p, it, u, s in lines:
            od.items.append(OrderItem(product_id=p.id, category_id=p.category_id, name=p.name, variation=" / ".join(x for x in (it.size, it.color) if x), qty=it.qty, unit_price=u, subtotal=s))
            p.stock -= it.qty
        if cp: cp.used_count += 1
        db.add(od); db.commit()
    except IntegrityError:
        db.rollback()
        if ex := db.scalar(select(Order).where(Order.idem_key == o.idem_key)): return done(ex)
        raise
    return done(od)

# ---------- loja pública ----------
@app.get("/api/store")
def store(db: Session = Depends(get_db)):
    st = db.get(Setting, 1)
    cats = db.scalars(select(Category).where(Category.active == True).order_by(Category.sort_order)).all()
    ids = {c.id for c in cats}
    prods = [p for p in db.scalars(select(Product).where(Product.active == True).order_by(Product.created_at.desc())).all() if p.category_id is None or p.category_id in ids]
    pj = lambda p: dict(id=p.id, name=p.name, description=p.description, price=p.price, promo_price=p.promo_price, category_id=p.category_id, stock=p.stock, sizes=p.sizes, colors=p.colors, images=[i.url for i in p.images], created_at=p.created_at)
    return dict(settings={k: getattr(st, k) for k in ("store_name", "whatsapp", "address", "hours", "moto_fee", "pix_key", "pay_info", "pickup_info", "socials", "logo_url", "banner_url")},
                categories=[dict(id=c.id, name=c.name, description=c.description, image=c.image) for c in cats], products=[pj(p) for p in prods])

# ---------- admin ----------
bearer = HTTPBearer()
def admin(cred: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)):
    try: a = db.get(Admin, int(jwt.decode(cred.credentials, SECRET, algorithms=["HS256"])["sub"]))
    except (jwt.PyJWTError, ValueError, KeyError): a = None
    if not a: raise HTTPException(401, "Não autorizado")
    return a
A = [Depends(admin)]

@app.post("/api/admin/login")
def login(b: LoginIn, db: Session = Depends(get_db)):
    a = db.scalar(select(Admin).where(Admin.email == b.email.lower()))
    h = a.password_hash.encode() if a else bcrypt.hashpw(b"x", bcrypt.gensalt())
    if not (bcrypt.checkpw(b.password.encode(), h) and a): raise HTTPException(401, "E-mail ou senha incorretos")
    return dict(token=jwt.encode({"sub": str(a.id), "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=8)}, SECRET, algorithm="HS256"))

def get_or_404(db, model, id):
    x = db.get(model, id)
    if not x: raise HTTPException(404, "Não encontrado")
    return x
def row(x): return {c.name: getattr(x, c.name) for c in x.__table__.columns}

@app.get("/api/admin/categories", dependencies=A)
def cats(db: Session = Depends(get_db)): return [row(c) for c in db.scalars(select(Category).order_by(Category.sort_order))]
@app.post("/api/admin/categories", status_code=201, dependencies=A)
def cat_new(b: CategoryIn, db: Session = Depends(get_db)):
    c = Category(**b.model_dump()); db.add(c); db.commit(); return row(c)
@app.put("/api/admin/categories/{id}", dependencies=A)
def cat_put(id: int, b: CategoryIn, db: Session = Depends(get_db)):
    c = get_or_404(db, Category, id)
    for k, v in b.model_dump().items(): setattr(c, k, v)
    db.commit(); return row(c)
@app.delete("/api/admin/categories/{id}", dependencies=A)
def cat_del(id: int, force: bool = False, db: Session = Depends(get_db)):
    snap(); c = get_or_404(db, Category, id); n = len(db.scalars(select(Product.id).where(Product.category_id == id)).all())
    if n and not force: raise HTTPException(409, f"Há {n} produto(s) nesta categoria. Confirme para excluir (force=true).")
    db.execute(update(Product).where(Product.category_id == id).values(category_id=None)); db.delete(c); db.commit(); return {"ok": True}

def pfill(p, b: ProductIn):
    if b.promo_price and b.promo_price >= b.price: raise HTTPException(422, "Preço promocional deve ser menor que o preço")
    for k, v in b.model_dump(exclude={"images"}).items(): setattr(p, k, v)
    if b.images is not None: p.images = [ProductImage(url=u, sort_order=i) for i, u in enumerate(b.images)]
def pout(p): return {**row(p), "images": [i.url for i in p.images]}
@app.get("/api/admin/products", dependencies=A)
def prods(q: str = "", db: Session = Depends(get_db)): return [pout(p) for p in db.scalars(select(Product).where(Product.name.ilike(f"%{q}%")).order_by(Product.id))]
@app.post("/api/admin/products", status_code=201, dependencies=A)
def prod_new(b: ProductIn, db: Session = Depends(get_db)):
    p = Product(); pfill(p, b); db.add(p); db.commit(); return pout(p)
@app.put("/api/admin/products/{id}", dependencies=A)
def prod_put(id: int, b: ProductIn, db: Session = Depends(get_db)):
    p = get_or_404(db, Product, id); pfill(p, b); db.commit(); return pout(p)
@app.delete("/api/admin/products/{id}", dependencies=A)
def prod_del(id: int, db: Session = Depends(get_db)):
    snap(); p = get_or_404(db, Product, id); db.execute(update(OrderItem).where(OrderItem.product_id == id).values(product_id=None)); db.delete(p); db.commit(); return {"ok": True}

@app.get("/api/admin/coupons", dependencies=A)
def coupons(db: Session = Depends(get_db)): return [row(c) for c in db.scalars(select(Coupon))]
@app.post("/api/admin/coupons", status_code=201, dependencies=A)
def cp_new(b: CouponIn, db: Session = Depends(get_db)):
    if b.kind == "percent" and b.value > 100: raise HTTPException(422, "Máximo 100%")
    c = Coupon(**{**b.model_dump(), "code": b.code.strip().upper()})
    db.add(c)
    try: db.commit()
    except IntegrityError: db.rollback(); raise HTTPException(409, "Código já existe")
    return row(c)
@app.put("/api/admin/coupons/{id}", dependencies=A)
def cp_put(id: int, b: CouponIn, db: Session = Depends(get_db)):
    c = get_or_404(db, Coupon, id)
    for k, v in {**b.model_dump(), "code": b.code.strip().upper()}.items(): setattr(c, k, v)
    db.commit(); return row(c)
@app.delete("/api/admin/coupons/{id}", dependencies=A)
def cp_del(id: int, db: Session = Depends(get_db)): db.delete(get_or_404(db, Coupon, id)); db.commit(); return {"ok": True}

def oj(o): return dict(number=o.id, date=o.created_at, status=o.status, customer=o.customer, ship=o.ship_method, cep=o.cep, pay=o.pay_method, pay_note=o.pay_note, notes=o.notes, internal_note=o.internal_note,
                       coupon=o.coupon_code, subtotal=o.subtotal, discount=o.discount, shipping=o.shipping, total=o.total, items=[dict(product_id=i.product_id, name=i.name, variation=i.variation, qty=i.qty, unit=i.unit_price, subtotal=i.subtotal) for i in o.items])
@app.get("/api/admin/orders", dependencies=A)
def orders(status: Optional[str] = None, number: Optional[int] = None, date_from: Optional[dt.date] = None, date_to: Optional[dt.date] = None, db: Session = Depends(get_db)):
    q = select(Order).order_by(Order.id.desc())
    if status: q = q.where(Order.status == status)
    if number: q = q.where(Order.id == number)
    if date_from: q = q.where(Order.created_at >= dt.datetime.combine(date_from, dt.time.min, dt.timezone.utc))
    if date_to: q = q.where(Order.created_at <= dt.datetime.combine(date_to, dt.time.max, dt.timezone.utc))
    return [oj(o) for o in db.scalars(q)]
@app.get("/api/admin/orders/{id}", dependencies=A)
def order_get(id: int, db: Session = Depends(get_db)): return oj(get_or_404(db, Order, id))
def _order_patch(id: int, b: OrderPatch, db: Session):
    o = get_or_404(db, Order, id)
    if b.status and b.status != o.status:
        sign = 1 if b.status == "Cancelado" else -1 if o.status == "Cancelado" else 0  # cancelar devolve estoque; reabrir baixa de novo
        for i in o.items:
            if sign and i.product_id and (p := db.get(Product, i.product_id)):
                if sign < 0 and p.stock < i.qty: raise HTTPException(409, f"Estoque insuficiente para reabrir: {p.name}")
                p.stock += sign * i.qty
        o.status = b.status
    if b.internal_note is not None: o.internal_note = b.internal_note
    if "shipping" in b.model_fields_set:  # frete confirmado (Correios/Transportadora)
        o.shipping = None if b.shipping is None else D(b.shipping); o.total = None if o.shipping is None else max(D(0), o.subtotal + o.shipping - o.discount)
    db.commit(); return oj(o)

@app.get("/api/admin/settings", dependencies=A)
def settings_get(db: Session = Depends(get_db)): return row(db.get(Setting, 1))
@app.put("/api/admin/settings", dependencies=A)
def settings_put(b: SettingsIn, db: Session = Depends(get_db)):
    s = db.get(Setting, 1)
    for k, v in b.model_dump().items(): setattr(s, k, v)
    db.commit(); return row(s)

@app.get("/api/admin/dashboard", dependencies=A)
def dashboard(year: Optional[int] = None, db: Session = Depends(get_db)):
    t = dt.date.today(); year = year or t.year; allo = db.scalars(select(Order)).all()
    rev = lambda o: o.total if o.total is not None else o.subtotal - o.discount
    done = [o for o in allo if o.status == "Concluído"]; valid = [o for o in allo if o.status != "Cancelado"]  # faturamento só de concluídos
    ym = lambda y, m: sum((rev(o) for o in done if o.created_at.year == y and o.created_at.month == m), D(0))
    py, pm = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
    yr = lambda y: sum((rev(o) for o in done if o.created_at.year == y), D(0))
    top, cv = {}, {}
    for o in valid:
        for i in o.items: top[i.name] = top.get(i.name, 0) + i.qty; cv[i.category_id] = cv.get(i.category_id, D(0)) + i.subtotal
    names = {c.id: c.name for c in db.scalars(select(Category))}; P = db.scalars(select(Product)).all()
    return dict(month=ym(t.year, t.month), prev_month=ym(py, pm), year=yr(t.year), prev_year=yr(t.year - 1), orders=len(allo), ticket=(sum((rev(o) for o in done), D(0)) / len(done)) if done else D(0),
                pending=sum(o.status not in ("Concluído", "Cancelado") for o in allo), completed=len(done), products=len(P), categories=len(names), available=sum(p.active and p.stock > 0 for p in P), out_of_stock=sum(p.stock < 1 for p in P),
                monthly=[ym(year, m) for m in range(1, 13)], orders_by_month=[sum(1 for o in valid if o.created_at.year == year and o.created_at.month == m) for m in range(1, 13)],
                top_products=sorted(top.items(), key=lambda x: -x[1])[:5], sales_by_category=[dict(category=names.get(k, "Sem categoria"), total=v) for k, v in cv.items()])

# SQLite não trava linhas: um cadeado serializa as operações que mexem em estoque (rode com 1 processo/worker).
import threading
LOCK = threading.Lock()
@app.post("/api/orders", status_code=201)
def create_order(o: OrderIn, db: Session = Depends(get_db)):
    with LOCK: return _create_order(o, db)
@app.patch("/api/admin/orders/{id}", dependencies=A)
def order_patch(id: int, b: OrderPatch, db: Session = Depends(get_db)):
    with LOCK: return _order_patch(id, b, db)

# ---------- site (loja em / e painel em /admin) ----------
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
STATIC = Path(__file__).resolve().parent.parent / "static"

@app.middleware("http")
async def sec_headers(request, call_next):
    r = await call_next(request); r.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "same-origin"}); return r

@app.get("/admin", include_in_schema=False)
def admin_page(): return FileResponse(STATIC / "admin.html")
app.mount("/", StaticFiles(directory=STATIC, html=True), name="site")  # sempre por último
