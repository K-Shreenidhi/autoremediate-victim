import json
import logging
import os
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class JsonFmt(logging.Formatter):
    def format(self, record):
        data = {
            "ts": round(time.time(), 3),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        data.update(getattr(record, "ctx", {}))
        if record.exc_info:
            data["trace"] = self.formatException(record.exc_info)
        return json.dumps(data)


log = logging.getLogger("orders")
log.setLevel(logging.INFO)
_handler = logging.FileHandler(os.getenv("LOG_FILE", "logs.jsonl"), encoding="utf-8")
_handler.setFormatter(JsonFmt())
log.addHandler(_handler)

app = FastAPI()

PRICES = {"sku-1": 20.0, "sku-2": 35.0}
DISCOUNTS = {"SAVE10": 10.0}
CUSTOMERS = {
    "c1": {"name": "Asha", "email": "asha@example.com"},
    "c2": {"name": "Ben", "email": None},
}
STOCK = {}
ORDERS = []
COUNTER = {"n": 0}


def reset_state():
    STOCK.clear()
    STOCK.update({"sku-1": 5, "sku-2": 0})
    ORDERS.clear()
    COUNTER["n"] = 0


reset_state()


class Order(BaseModel):
    sku: str
    qty: int
    code: str | None = None


def discount_pct(code):
    if not code:
        return 0.0
    pct = DISCOUNTS.get(code)
    if pct is None:
        log.warning("unknown discount code", extra={"ctx": {"code": code}})
        return 0.0
    return pct


@app.middleware("http")
async def trace(request: Request, call_next):
    rid = uuid.uuid4().hex[:8]
    try:
        resp = await call_next(request)
    except Exception:
        log.exception(
            "unhandled exception",
            extra={"ctx": {"request_id": rid, "method": request.method, "path": request.url.path}},
        )
        return JSONResponse({"error": "internal"}, status_code=500)
    log.info(
        "request",
        extra={"ctx": {"request_id": rid, "method": request.method, "path": request.url.path, "status": resp.status_code}},
    )
    return resp


@app.post("/orders")
def create_order(o: Order):
    if o.sku not in PRICES:
        raise HTTPException(404, "unknown sku")
    if o.qty < 1:
        raise HTTPException(422, "qty must be >= 1")
    if o.qty > STOCK[o.sku]:
        raise HTTPException(409, "insufficient stock")
    pct = discount_pct(o.code)
    total = round(PRICES[o.sku] * o.qty * (1 - pct / 100), 2)
    STOCK[o.sku] -= o.qty
    COUNTER["n"] += 1
    order = {"id": COUNTER["n"], "sku": o.sku, "qty": o.qty, "total": total}
    ORDERS.append(order)
    log.info(
        "order_created",
        extra={"ctx": {"order_id": order["id"], "sku": o.sku, "qty": o.qty, "stock_remaining": STOCK[o.sku]}},
    )
    return order


@app.get("/orders")
def list_orders(page: int = 1, page_size: int = 2):
    start = (page - 1) * page_size
    items = ORDERS[start : start + page_size]
    log.info(
        "list_orders",
        extra={"ctx": {"page": page, "page_size": page_size, "returned": len(items), "total_orders": len(ORDERS)}},
    )
    return {"items": items}


@app.delete("/orders/{order_id}")
def delete_order(order_id: int):
    for i, order in enumerate(ORDERS):
        if order["id"] == order_id:
            ORDERS.pop(i)
            return {"deleted": order_id}
    raise HTTPException(404, "order not found")


@app.get("/customers/{cid}")
def get_customer(cid: str):
    c = CUSTOMERS.get(cid)
    if c is None:
        raise HTTPException(404, "customer not found")
    domain = c["email"].split("@")[1] if c["email"] else None
    return {"name": c["name"], "email_domain": domain}