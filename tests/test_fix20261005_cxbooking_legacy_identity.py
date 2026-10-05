import datetime
import pytest
from checkout_helpers import quote_confirmation
from services.auth_service import AuthService
from models.parking_session import ParkingSession
from core.vehicle_identity import canonical_identity

REF = datetime.datetime(2026, 8, 25, 1, 35, 34)


@pytest.fixture()
def business_reference_now():
    return REF


@pytest.fixture(autouse=True)
def freeze(monkeypatch):
    import crud.parking_session as m
    monkeypatch.setattr(m, "server_now", lambda: REF + datetime.timedelta(minutes=30))


@pytest.fixture
def headers(test_user):
    tok = AuthService().create_access_token(user_id=test_user.id, username=test_user.username,
                                            role=str(test_user.role), password_hash=test_user.password_hash)
    return {"Authorization": f"Bearer {tok}"}


def test_legacy_search_and_checkout_plate_variants(client, headers, vehicle, parking_session, vehicle_type, parking_slot, db_session):
    print("\nstored plate:", vehicle.license_plate)
    variants = ["30A-999.99", "30A99999", "30a 999 99", "30A-99999", "30A-999"]
    results = {}
    for q in variants:
        r = client.get("/parking/search", params={"license_plate": q}, headers=headers)
        results[q] = (r.status_code, r.json().get("total"))
        print(f"search {q!r} -> {r.status_code} total={r.json().get('total')} canonical_equal={canonical_identity(q)==canonical_identity(vehicle.license_plate)}")
    # admission treats the variant as same vehicle
    r = client.post("/parking/check-in", json={"license_plate": "30A99999", "vehicle_type_id": vehicle_type.id}, headers=headers)
    print("check-in variant while parked:", r.status_code, r.json())
    # legacy check-out with variant
    conf = quote_confirmation(client, headers, parking_session.id)
    r = client.post("/parking/check-out", json={"license_plate": "30A99999", **conf}, headers=headers)
    print("legacy check-out with variant:", r.status_code, r.json())
    variant_checkout = r.status_code
    # same quote with exact stored spelling still works
    r2 = client.post("/parking/check-out", json={"license_plate": vehicle.license_plate, **conf}, headers=headers)
    print("legacy check-out with stored spelling:", r2.status_code, r2.json().get("status"))
    # PUT path (UI path) has no plate comparison
    assert results["30A-999.99"][1] == 1
    assert results["30A99999"][1] == 1
    assert results["30a 999 99"][1] == 1
    assert variant_checkout == 200
