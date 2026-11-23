import os, sqlite3, threading, time
from datetime import datetime
from pathlib import Path
from .models import URL, ROOT, engine

KEEP = int(os.getenv("BACKUP_KEEP", "14"))
DIR = Path(os.getenv("BACKUP_DIR") or ROOT / "backups")
_last, _lock = 0.0, threading.Lock()

def make_backup(min_interval: float = 0):
    """Copia o banco SQLite (seguro mesmo com a loja em uso) para backups/ e mantém só as últimas KEEP cópias."""
    global _last
    if not URL.startswith("sqlite"): return None
    with _lock:
        if time.time() - _last < min_interval: return None
        DIR.mkdir(parents=True, exist_ok=True)
        dest = DIR / f"mateus-{datetime.now():%Y%m%d-%H%M%S}.db"
        src, dst = sqlite3.connect(engine.url.database), sqlite3.connect(dest)
        try: src.backup(dst)
        finally: dst.close(); src.close()
        _last = time.time()
        for old in sorted(DIR.glob("mateus-*.db"))[:-KEEP]: old.unlink()
        return dest

def snap():
    """Backup de segurança antes de exclusões (no máximo 1 a cada 20 segundos)."""
    if os.getenv("BACKUP", "1") == "0": return
    try: make_backup(20)
    except Exception as e: print("Falha no backup:", e)

def start_scheduler(hours: float = 6):
    def loop():
        while True:
            time.sleep(hours * 3600)
            snap_all()
    def snap_all():
        try: make_backup()
        except Exception as e: print("Falha no backup:", e)
    threading.Thread(target=loop, daemon=True).start()
