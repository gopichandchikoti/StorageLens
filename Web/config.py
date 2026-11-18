"""Asset/state separation for source, installed desktop and isolated test runs."""
import json
import os
from pathlib import Path
import shutil
import sys

ASSETS = Path(__file__).resolve().parent
if os.environ.get('STORAGELENS_DATA_DIR'):
    DATA = Path(os.environ['STORAGELENS_DATA_DIR']).expanduser().resolve()
elif getattr(sys, 'frozen', False):
    DATA = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'StorageLens' / 'data'
else:
    DATA = ASSETS.parent / '.data'
DATA.mkdir(parents=True, exist_ok=True)
INVENTORY = DATA / 'inventory.json'
legacy_inventory = ASSETS.parent / 'inventory.json'
if not INVENTORY.exists() and DATA == ASSETS.parent / '.data' and legacy_inventory.is_file():
    shutil.copy2(legacy_inventory, INVENTORY)

SESSION = os.environ.get('STORAGELENS_SESSION_TOKEN', '')

def product():
    path = ASSETS / 'product.json'
    if not path.exists():
        path = ASSETS.parent / 'product.json'
    return json.loads(path.read_text(encoding='utf-8'))
