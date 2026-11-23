import json
from .models import *

def seed_if_empty(db) -> int:
    """Importa data/catalogo.json se o banco ainda não tem produtos. Retorna quantos produtos entraram."""
    f = ROOT / "data" / "catalogo.json"
    if not f.exists() or db.query(Product).count(): return 0
    seed = json.loads(f.read_text(encoding="utf-8"))
    st = db.get(Setting, 1) or Setting(id=1)
    db.add(st)
    if not st.whatsapp: st.whatsapp, st.address, st.pickup_info, st.socials = seed["s"]["wa"], seed["s"]["addr"], seed["s"]["pickup"], seed["s"]["insta"]
    ids = {}
    for c in seed["cats"]:
        o = Category(name=c["name"], sort_order=c["ord"], active=c["on"]); db.add(o); db.flush(); ids[c["id"]] = o.id
    for p in seed["prods"]:
        db.add(Product(name=p["name"], price=p["price"], promo_price=p["promo"] or None, category_id=ids[p["cat"]], stock=p["stock"], sizes=p["sizes"], colors=p["colors"],
                       images=[ProductImage(url=u, sort_order=i) for i, u in enumerate(p["imgs"])]))
    db.commit()
    return len(seed["prods"])
