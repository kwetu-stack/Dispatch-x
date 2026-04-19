import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import Dispatch, Stop, User, app, db


def login(client, phone, password):
    return client.post("/login", data={"phone": phone, "password": password}, follow_redirects=True)


def assert_ok(response, path):
    assert response.status_code == 200, f"{path} returned {response.status_code}"


def run():
    with app.app_context():
        active_dispatch = Dispatch.query.filter_by(is_deleted=False).order_by(Dispatch.id.desc()).first()
        assert active_dispatch, "No active dispatch found for smoke test."
        driver_dispatch = (
            Dispatch.query.filter_by(is_deleted=False, status="in_progress")
            .join(Stop)
            .filter(Stop.status == "pending")
            .order_by(Dispatch.id.desc())
            .first()
        )
        assert driver_dispatch, "No active in-progress dispatch with pending stops found for smoke test."
        driver = db.session.get(User, driver_dispatch.driver_id)
        assert driver, "Smoke test dispatch has no driver."
        pending_stop = (
            Stop.query.filter_by(dispatch_id=driver_dispatch.id, status="pending")
            .order_by(Stop.sequence)
            .first()
        )

    with app.test_client() as client:
        assert_ok(client.get("/login"), "/login")
        login(client, "0700000001", "admin123")
        for path in ["/", "/dispatches", f"/dispatches/{active_dispatch.id}", "/gps"]:
            assert_ok(client.get(path), path)

    with app.test_client() as client:
        login(client, driver.phone, "driver123")
        assert_ok(client.get("/driver"), "/driver")
        stop_path = f"/driver/stop/{pending_stop.id}"
        stop_response = client.get(stop_path)
        assert_ok(stop_response, stop_path)
        stop_html = stop_response.get_data(as_text=True)
        assert "Take Proof & Deliver" in stop_html
        assert 'name="proof_photo"' in stop_html
        assert 'accept="image/*"' in stop_html
        assert 'capture="environment"' in stop_html
        with open("static/js/stop_detail.js", encoding="utf-8") as handle:
            stop_js = handle.read()
        assert "Upload Proof Photo" in stop_js
        assert "navigator.geolocation.getCurrentPosition" in stop_js
        assert "Location permission required to save delivery." in stop_js
        assert "navigator.mediaDevices.getUserMedia" in stop_js
        gps = client.post("/api/gps", json={"latitude": -1.28, "longitude": 36.82})
        assert gps.status_code in {200, 409}, f"/api/gps returned {gps.status_code}"

    print("Smoke tests passed.")


if __name__ == "__main__":
    run()
