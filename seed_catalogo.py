"""Importa o catálogo manualmente (o servidor já faz isso sozinho na primeira vez). Uso: python seed_catalogo.py"""
from app.models import *
from app.seed import seed_if_empty
Base.metadata.create_all(engine)
with SessionLocal() as db:
    n = seed_if_empty(db)
    print(f"{n} produtos importados." if n else "O banco já tem produtos (ou data/catalogo.json não existe); nada foi importado.")
