from dotenv import load_dotenv; load_dotenv()
import os, datetime as dt
from decimal import Decimal
from typing import Optional
from sqlalchemy import event, create_engine, String, Text, Integer, Numeric, Boolean, ForeignKey, JSON, Date, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

URL = os.getenv("DATABASE_URL", "sqlite:///./mateus.db")
engine = create_engine(URL, pool_pre_ping=True, connect_args={"check_same_thread": False} if URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(engine, expire_on_commit=False)
if URL.startswith("sqlite"):  # integridade referencial, escrita segura e espera em vez de erro "database is locked"
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(conn, _):
        cur = conn.cursor(); cur.execute("PRAGMA foreign_keys=ON"); cur.execute("PRAGMA journal_mode=WAL"); cur.execute("PRAGMA busy_timeout=5000"); cur.close()
def get_db():
    with SessionLocal() as s:
        yield s

class Base(DeclarativeBase): pass
M = lambda: Numeric(10, 2)
now = lambda: dt.datetime.now(dt.timezone.utc)

class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))

class Setting(Base):
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    store_name: Mapped[str] = mapped_column(String(120), default="Mateus Imports")
    whatsapp: Mapped[str] = mapped_column(String(30), default="")
    address: Mapped[str] = mapped_column(String(250), default="")
    hours: Mapped[str] = mapped_column(String(160), default="")
    moto_fee: Mapped[Decimal] = mapped_column(M(), default=Decimal("0"))
    pix_key: Mapped[str] = mapped_column(String(160), default="")
    pay_info: Mapped[str] = mapped_column(Text, default="")
    pickup_info: Mapped[str] = mapped_column(Text, default="")
    socials: Mapped[str] = mapped_column(String(250), default="")
    logo_url: Mapped[str] = mapped_column(Text, default="")
    banner_url: Mapped[str] = mapped_column(Text, default="")

class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    image: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(default=0)
    active: Mapped[bool] = mapped_column(default=True)

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[Decimal] = mapped_column(M())
    promo_price: Mapped[Optional[Decimal]] = mapped_column(M())
    stock: Mapped[int] = mapped_column(default=0)
    sizes: Mapped[list] = mapped_column(JSON, default=list)
    colors: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    images: Mapped[list["ProductImage"]] = relationship(order_by="ProductImage.sort_order", cascade="all, delete-orphan", lazy="selectin")

class ProductImage(Base):
    __tablename__ = "product_images"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(default=0)

class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(30))

class Coupon(Base):
    __tablename__ = "coupons"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    kind: Mapped[str] = mapped_column(String(10))  # percent | fixed
    value: Mapped[Decimal] = mapped_column(M())
    expires_on: Mapped[Optional[dt.date]] = mapped_column(Date)
    max_uses: Mapped[Optional[int]]
    min_purchase: Mapped[Decimal] = mapped_column(M(), default=Decimal("0"))
    used_count: Mapped[int] = mapped_column(default=0)
    active: Mapped[bool] = mapped_column(default=True)

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)  # id = número do pedido
    idem_key: Mapped[str] = mapped_column(String(80), unique=True)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"))
    customer: Mapped[dict] = mapped_column(JSON)
    ship_method: Mapped[str] = mapped_column(String(20))
    cep: Mapped[str] = mapped_column(String(12), default="")
    pay_method: Mapped[str] = mapped_column(String(30))
    pay_note: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    internal_note: Mapped[str] = mapped_column(Text, default="")
    coupon_code: Mapped[str] = mapped_column(String(40), default="")
    subtotal: Mapped[Decimal] = mapped_column(M())
    discount: Mapped[Decimal] = mapped_column(M(), default=Decimal("0"))
    shipping: Mapped[Optional[Decimal]] = mapped_column(M())  # NULL = frete a confirmar
    total: Mapped[Optional[Decimal]] = mapped_column(M())
    status: Mapped[str] = mapped_column(String(40), default="Aguardando confirmação", index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    items: Mapped[list["OrderItem"]] = relationship(cascade="all, delete-orphan", lazy="selectin")

class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    category_id: Mapped[Optional[int]]
    name: Mapped[str] = mapped_column(String(200))
    variation: Mapped[str] = mapped_column(String(120), default="")
    qty: Mapped[int]
    unit_price: Mapped[Decimal] = mapped_column(M())
    subtotal: Mapped[Decimal] = mapped_column(M())
