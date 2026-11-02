"""The betslip synced to a signed-in account (app/slip_sync.py): save, read back, refuse a stale save, limits, privacy."""
import re

import pytest
from fastapi.testclient import TestClient

from app import auth, main
from app.db import SessionLocal, UserSlip

LEG = {"id": "p1|rush|Over|64.5|DraftKings", "playerId": "p1", "kind": "rush", "line": 64.5, "book": "DraftKings"}


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(auth, "send_email", lambda to, subject, text, html: out.append(re.search(r"#t=([\w-]+)", text).group(1)))
    auth._hits.clear()
    return out


def device(sent, email, ip, confirm=True):
    """A browser signed in to `email` (each call is a separate device with its own session)."""
    c = TestClient(main.app, client=(ip, 5000))
    c.post("/api/auth/email", json={"email": email})
    c.post("/api/auth/email/verify", json={"token": sent[-1]})
    if confirm:
        c.post("/api/auth/age")
    return c


def test_a_slip_follows_the_account_to_another_device(sent):
    with device(sent, "slipper@example.com", "198.51.100.60") as phone, device(sent, "slipper@example.com", "198.51.100.61") as laptop:
        assert phone.get("/api/me/slip").json() == {"legs": [], "stakes": {}, "updated_at": None}
        saved = phone.put("/api/me/slip", json={"legs": [LEG], "stakes": {"DraftKings": 20}}).json()
        assert saved["legs"] == [LEG] and saved["stakes"] == {"DraftKings": 20} and saved["updated_at"]
        assert laptop.get("/api/me/slip").json() == saved


def test_a_save_based_on_an_older_copy_is_refused_with_the_newer_one(sent):
    with device(sent, "racer@example.com", "198.51.100.62") as a, device(sent, "racer@example.com", "198.51.100.63") as b:
        first = a.put("/api/me/slip", json={"legs": [LEG], "stakes": {}}).json()
        b.put("/api/me/slip", json={"legs": [], "stakes": {}, "base": first["updated_at"]})   # b read the first copy, then emptied it
        stale = a.put("/api/me/slip", json={"legs": [LEG, {**LEG, "id": "p2"}], "stakes": {}, "base": first["updated_at"]})
        assert stale.status_code == 409 and stale.json()["legs"] == []   # a gets b's newer copy to merge, nothing is overwritten
        fresh = a.put("/api/me/slip", json={"legs": [LEG], "stakes": {}, "base": stale.json()["updated_at"]})
        assert fresh.status_code == 200


def test_slip_limits_and_who_may_use_it(sent):
    with device(sent, "limits@example.com", "198.51.100.64") as c:
        assert c.put("/api/me/slip", json={"legs": [{**LEG, "id": str(i)} for i in range(41)], "stakes": {}}).status_code == 422
        assert c.put("/api/me/slip", json={"legs": [{"no": "id"}], "stakes": {}}).status_code == 422
        assert c.put("/api/me/slip", json={"legs": [{**LEG, "pad": "x" * 70_000}], "stakes": {}}).status_code == 422
        assert c.put("/api/me/slip", headers={"Origin": "https://evil.example"}, json={"legs": [], "stakes": {}}).status_code == 403
    with TestClient(main.app, client=("198.51.100.65", 5000)) as anon:
        assert anon.get("/api/me/slip").status_code == 401
    with device(sent, "young2@example.com", "198.51.100.66", confirm=False) as young:
        assert young.get("/api/me/slip").status_code == 403     # 21+ first, as for tracked bets
    with device(sent, "other@example.com", "198.51.100.67") as other:
        assert other.get("/api/me/slip").json()["legs"] == []   # one account never sees another's slip


def test_deleting_the_account_deletes_its_slip(sent):
    from app.db import User
    with device(sent, "goner@example.com", "198.51.100.68") as c:
        c.put("/api/me/slip", json={"legs": [LEG], "stakes": {}})
        with SessionLocal() as s:
            uid = s.query(User).filter(User.email == "goner@example.com").one().id
            assert s.get(UserSlip, uid) is not None
        c.delete("/api/auth/me")
    with SessionLocal() as s:
        assert s.get(UserSlip, uid) is None
