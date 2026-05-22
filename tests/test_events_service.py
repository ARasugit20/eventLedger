

from app.services.events import stable_payload_hash


def test_stable_payload_hash_is_deterministic():
    payload = {"sku": "X1", "quantity": 2}
    a = stable_payload_hash(payload)
    b = stable_payload_hash({"quantity": 2, "sku": "X1"})
    assert a == b
    assert len(a) == 16


def test_stable_payload_hash_differs_for_different_payloads():
    a = stable_payload_hash({"sku": "A"})
    b = stable_payload_hash({"sku": "B"})
    assert a != b
