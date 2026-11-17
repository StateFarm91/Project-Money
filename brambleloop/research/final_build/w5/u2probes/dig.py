import hashlib, json
from brambleloop.products import inventory
for s in ["heart-row-ring-pillow","spring-garden-kneeler","market-basket-medium","market-basket-large","cloudline-baby-blanket","nordic-forest-mosaic-throw-baby"]:
    try:
        c = inventory._engineered(s)
        print(s, hashlib.sha256(json.dumps(c.to_dict(), sort_keys=True, separators=(",",":"), allow_nan=False).encode()).hexdigest()[:16])
    except Exception as e: print(s, "ERR", type(e).__name__, str(e)[:80])
