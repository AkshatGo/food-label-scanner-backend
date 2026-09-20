"""End-to-end API tests — exercises the doc 07 surface with the real app."""

import io
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def auth_headers(client):
    signup = client.post("/api/v1/auth/signup", json={
        "email": f"tester-{time.time_ns()}@example.com", "password": "password123",
    })
    assert signup.status_code == 201, signup.text
    token = signup.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _png_bytes(color=(200, 100, 50), size=(600, 800)):
    """A realistic stand-in for a label photo: solid color plus printed text.

    The OpenCV blur gate correctly rejects pure flat-color uploads (variance
    of the Laplacian is 0.0 — no edges means no text to read), so fixtures
    carry renderable text like a real packet photo would.
    """
    buffer = io.BytesIO()
    image = Image.new("RGB", size, color)
    ImageDraw.Draw(image).text((30, 30), "Nutrition Energy 450 kcal", fill="white")
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _scan(client, auth_headers, back_text_image=None):
    files = {
        "front_image": ("front.png", io.BytesIO(_png_bytes()), "image/png"),
        "back_image": ("back.png", io.BytesIO(back_text_image or _png_bytes()), "image/png"),
    }
    return client.post("/api/v1/scan", files=files, headers=auth_headers)


def _wait_for_scan(client, scan_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        poll = client.get(f"/api/v1/scan/{scan_id}")
        if poll.status_code == 200 and poll.json().get("status") != "processing":
            return poll.json()
        time.sleep(0.5)
    raise TimeoutError(f"Scan {scan_id} did not finish in {timeout}s")


# --- Health & auth ----------------------------------------------------------------

def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "LabelLens" in response.json()["message"]


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_signup_login_flow(client):
    signup = client.post("/api/v1/auth/signup", json={
        "email": "flow@example.com", "password": "password123",
    })
    assert signup.status_code == 201
    login = client.post("/api/v1/auth/login", json={
        "email": "flow@example.com", "password": "password123",
    })
    assert login.status_code == 200
    assert login.json()["user_id"] == signup.json()["user_id"]


def test_signup_duplicate_409(client):
    client.post("/api/v1/auth/signup", json={"email": "dup@example.com", "password": "password123"})
    again = client.post("/api/v1/auth/signup", json={"email": "dup@example.com", "password": "password123"})
    assert again.status_code == 409
    assert again.json()["detail"]["error"]["code"] == "CONFLICT"


def test_conditions_update_and_validation(client, auth_headers):
    # fetch user id from token payload via /users endpoint using a fresh signup
    signup = client.post("/api/v1/auth/signup", json={
        "email": f"cond-{time.time_ns()}@example.com", "password": "password123",
    })
    user_id = signup.json()["user_id"]
    headers = {"Authorization": f"Bearer {signup.json()['token']}"}

    put = client.put(f"/api/v1/users/{user_id}/conditions", json={
        "conditions": ["diabetes", "migraine"]
    }, headers=headers)
    assert put.status_code == 200
    assert put.json()["conditions"] == ["diabetes", "migraine"]

    invalid = client.put(f"/api/v1/users/{user_id}/conditions", json={
        "conditions": ["common cold"]
    }, headers=headers)
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["error"]["code"] == "INVALID_CONDITION"


def test_protected_endpoint_requires_token(client):
    response = client.post("/api/v1/compare", json={
        "product_id_a": "p_x", "product_id_b": "p_y",
    })
    assert response.status_code == 401


# --- Scan flow ----------------------------------------------------------------------

def test_scan_full_flow(client, auth_headers):
    response = _scan(client, auth_headers)
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "processing"
    assert body["scan_id"]

    result = _wait_for_scan(client, body["scan_id"])
    assert result["status"] == "done"
    assert "product" in result
    product = result["product"]
    assert product["product_id"]
    assert product["category"] in ("I", "II", "III")
    assert "inr" in product
    assert "formula_version" in product["inr"]
    assert "compliance" in product or result.get("needs_review") is not None


def test_scan_requires_both_images(client, auth_headers):
    files = {"front_image": ("front.png", io.BytesIO(_png_bytes()), "image/png")}
    response = client.post("/api/v1/scan", files=files, headers=auth_headers)
    assert response.status_code == 422  # FastAPI validation: back_image missing


def test_scan_rejects_non_image(client, auth_headers):
    files = {
        "front_image": ("front.txt", io.BytesIO(b"not an image"), "text/plain"),
        "back_image": ("back.txt", io.BytesIO(b"not an image"), "text/plain"),
    }
    response = client.post("/api/v1/scan", files=files, headers=auth_headers)
    assert response.status_code == 400


def test_scan_unknown_id_404(client, auth_headers):
    assert client.get("/api/v1/scan/SCAN-NOPE", headers=auth_headers).status_code == 404


# --- Product, compare, personalize ---------------------------------------------------

@pytest.fixture()
def scanned_product_id(client, auth_headers):
    response = _scan(client, auth_headers)
    scan_id = response.json()["scan_id"]
    result = _wait_for_scan(client, scan_id)
    return result["product"]["product_id"]


def test_get_product(client, auth_headers, scanned_product_id):
    response = client.get(f"/api/v1/product/{scanned_product_id}", headers=auth_headers)
    assert response.status_code == 200
    product = response.json()
    assert product["product_id"] == scanned_product_id
    assert "nutrition_per_100g" in product
    assert "inr" in product


def test_get_product_404(client, auth_headers):
    assert client.get("/api/v1/product/p_missing", headers=auth_headers).status_code == 404


def test_compare(client, auth_headers, scanned_product_id):
    second = _scan(client, auth_headers)
    second_id = _wait_for_scan(client, second.json()["scan_id"])["product"]["product_id"]

    response = client.post("/api/v1/compare", json={
        "product_id_a": scanned_product_id, "product_id_b": second_id,
    }, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["product_a"]["product_id"] == scanned_product_id
    assert body["product_b"]["product_id"] == second_id
    assert "inr_stars" in body["product_a"]


def test_personalize_with_explicit_conditions(client, auth_headers, scanned_product_id):
    response = client.post("/api/v1/personalize", json={
        "product_id": scanned_product_id,
        "conditions": ["diabetes", "migraine"],
    }, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["product_id"] == scanned_product_id
    assert "not a medical device" in body["disclaimer"]
    verdicts = {v["condition"]: v["verdict"] for v in body["verdicts"]}
    assert set(verdicts) == {"diabetes", "migraine"}
    assert all(v in ("GOOD_FIT", "CAUTION", "AVOID") for v in verdicts.values())


def test_personalize_rejects_invalid_condition(client, auth_headers, scanned_product_id):
    response = client.post("/api/v1/personalize", json={
        "product_id": scanned_product_id, "conditions": ["flu"],
    }, headers=auth_headers)
    assert response.status_code == 422
    assert response.json()["detail"]["error"]["code"] == "INVALID_CONDITION"


def test_personalize_uses_profile_conditions(client, auth_headers):
    signup = client.post("/api/v1/auth/signup", json={
        "email": f"prof-{time.time_ns()}@example.com", "password": "password123",
    })
    user_id = signup.json()["user_id"]
    headers = {"Authorization": f"Bearer {signup.json()['token']}"}
    client.put(f"/api/v1/users/{user_id}/conditions", json={"conditions": ["fever"]}, headers=headers)

    scan = _scan(client, headers)
    product_id = _wait_for_scan(client, scan.json()["scan_id"])["product"]["product_id"]

    response = client.post("/api/v1/personalize", json={"product_id": product_id}, headers=headers)
    assert response.status_code == 200
    assert [v["condition"] for v in response.json()["verdicts"]] == ["fever"]


# --- Compliance report ----------------------------------------------------------------

def test_compliance_report_summary(client, auth_headers, scanned_product_id):
    response = client.get(
        f"/api/v1/compliance-report/{scanned_product_id}/summary", headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["product_id"] == scanned_product_id
    assert "Version VII" in body["regulation_version"]
    assert "font_size_summary" in body
    assert "declarations_summary" in body
    assert "not a legal compliance certification" in body["overall_note"]


def test_compliance_report_pdf(client, auth_headers, scanned_product_id):
    response = client.get(
        f"/api/v1/compliance-report/{scanned_product_id}", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:5] == b"%PDF-"
    assert len(response.content) > 1000


def test_compliance_pdf_regenerate(client, auth_headers, scanned_product_id):
    first = client.get(f"/api/v1/compliance-report/{scanned_product_id}", headers=auth_headers)
    second = client.get(
        f"/api/v1/compliance-report/{scanned_product_id}?regenerate=true", headers=auth_headers
    )
    assert first.status_code == second.status_code == 200
    assert first.content[:5] == second.content[:5] == b"%PDF-"


# --- Error shape (doc 07) ---------------------------------------------------------------

def test_error_shape_standard(client):
    response = client.get("/api/v1/product/p_missing", headers={"Authorization": "Bearer bad"})
    # 401 from token validation
    body = response.json()
    if response.status_code != 401:
        assert "error" in body["detail"]
    else:
        assert body["detail"]["error"]["code"] in ("UNAUTHORIZED",)
