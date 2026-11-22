"""Importa as categorias e produtos de data/catalogo.json para o banco. Uso: python seed_catalogo.py"""
import json
from pathlib import Path
from app.models import *
seed = json.loads((Path(__file__).parent / "data" / "catalogo.json").read_text(encoding="utf-8"))
Base.metadata.create_all(engine)
with SessionLocal() as db:
    if db.query(Product).count(): raise SystemExit("O banco já tem produtos; importação cancelada para não duplicar.")
    st = db.get(Setting, 1) or Setting(id=1); db.add(st)
    st.whatsapp, st.address, st.pickup_info, st.socials = seed["s"]["wa"], seed["s"]["addr"], seed["s"]["pickup"], seed["s"]["insta"]
    ids = {}
    for c in seed["cats"]:
        o = Category(name=c["name"], sort_order=c["ord"], active=c["on"]); db.add(o); db.flush(); ids[c["id"]] = o.id
    for p in seed["prods"]:
        db.add(Product(name=p["name"], price=p["price"], promo_price=p["promo"] or None, category_id=ids[p["cat"]], stock=p["stock"], sizes=p["sizes"], colors=p["colors"],
                       images=[ProductImage(url=u, sort_order=i) for i, u in enumerate(p["imgs"])]))
    db.commit(); print(len(seed["cats"]), "categorias e", len(seed["prods"]), "produtos importados")
