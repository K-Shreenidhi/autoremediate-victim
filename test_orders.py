import pytest
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def fresh_state():
    main.reset_state()


def place(sku="sku-1", qty=1, code=None):
    return client.post("/orders", json={"sku": sku, "qty": qty, "code": code})


def test_order_total_no_code():
    r = place(qty=2)
    assert r.status_code == 200
    assert r.json()["total"] == 40.0


def test_valid_code_applies_discount():
    r = place(code="SAVE10")
    assert r.status_code == 200
    assert r.json()["total"] == 18.0


def test_unknown_code_ignored():
    r = place(code="BOGUS")
    assert r.status_code == 200
    assert r.json()["total"] == 20.0


def test_insufficient_stock_rejected():
    r = place(sku="sku-2", qty=1)
    assert r.status_code == 409


def test_stock_decrements_and_blocks_oversell():
    assert place(qty=5).status_code == 200
    assert place(qty=1).status_code == 409


def test_list_orders_pagination():
    for _ in range(3):
        place()
    first = client.get("/orders", params={"page": 1, "page_size": 2}).json()["items"]
    second = client.get("/orders", params={"page": 2, "page_size": 2}).json()["items"]
    assert [o["id"] for o in first] == [1, 2]
    assert [o["id"] for o in second] == [3]


def test_delete_existing_order():
    place()
    r = client.delete("/orders/1")
    assert r.status_code == 200
    assert r.json() == {"deleted": 1}


def test_delete_missing_order_returns_404():
    r = client.delete("/orders/99")
    assert r.status_code == 404


def test_customer_with_email():
    r = client.get("/customers/c1")
    assert r.status_code == 200
    assert r.json()["email_domain"] == "example.com"


def test_customer_without_email():
    r = client.get("/customers/c2")
    assert r.status_code == 200
    assert r.json()["email_domain"] is None


def test_unknown_customer_404():
    r = client.get("/customers/nope")
    assert r.status_code == 404