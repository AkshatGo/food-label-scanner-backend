"""Live smoke test: exercises every endpoint against a running server.

Usage: .venv/bin/python scripts/smoke_test.py [base_url]
"""

import io
import sys
import time

import requests

# Preserve the HttpOnly session issued at signup for all protected reads.
requests = requests.Session()

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099"

# --- 1. Health ----------------------------------------------------------------
r = requests.get(f"{BASE}/")
assert r.status_code == 200, r.text
print("[1] root:", r.json())

r = requests.get(f"{BASE}/health")
assert r.status_code == 200
print("[2] health:", r.json())

# --- 2. Render a real label image (OCR runs over it) -----------------------------
from PIL import Image, ImageDraw

img = Image.new("RGB", (760, 1100), "white")
draw = ImageDraw.Draw(img)
lines = [
    "Crunchy Biscuits", "Brand: ACME", "",
    "Ingredients: Wheat Flour (Maida), Sugar, Palm Oil,",
    "Invert Sugar Syrup, Raising Agent (INS 500),",
    "Emulsifier (Soya Lecithin INS 322), Salt, Milk Solids",
    "Contains Wheat, Milk and Soya",
    "Nutritional Information per 100g",
    "Energy 480 kcal", "Protein 6 g", "Total Carbohydrate 62 g",
    "Total Sugars 18 g", "Added Sugars 15 g", "Total Fat 20 g",
    "Saturated Fat 6 g", "Sodium 420 mg", "Dietary Fibre 2 g",
    "Net weight 100g", "MRP Rs 40", "Manufactured by ACME Foods Pvt Ltd Mumbai",
    "FSSAI Lic. No. 10012345678901", "Batch No. B123",
    "Best Before 6 months from packaging",
    "Consumer Care: 1800-123-456", "Store in a cool dry place",
]
y = 20
for line in lines:
    draw.text((30, y), line, fill="black")
    y += 40
front = Image.new("RGB", (760, 500), "white")
ImageDraw.Draw(front).text((30, 30), "Crunchy Biscuits", fill="black")
front_buf = io.BytesIO(); front.save(front_buf, format="PNG")
back_buf = io.BytesIO(); img.save(back_buf, format="PNG")

# --- 3. Auth ---------------------------------------------------------------------
email = f"smoke-{int(time.time())}@example.com"
r = requests.post(f"{BASE}/api/v1/auth/signup",
                  json={"email": email, "password": "password123"})
assert r.status_code == 201, r.text
token = r.json()["token"]
user_id = r.json()["user_id"]
print(f"[3] signup OK (user {user_id})")

r = requests.post(f"{BASE}/api/v1/auth/login",
                  json={"email": email, "password": "password123"})
assert r.status_code == 200
print("[4] login OK")

headers = {"Authorization": f"Bearer {token}"}

r = requests.put(f"{BASE}/api/v1/users/{user_id}/conditions",
                 json={"conditions": ["diabetes", "migraine"]}, headers=headers)
assert r.status_code == 200, r.text
print("[5] conditions set:", r.json()["conditions"])

# --- 4. Scan ----------------------------------------------------------------------
r = requests.post(f"{BASE}/api/v1/scan",
                  files={"front_image": ("front.png", front_buf.getvalue(), "image/png"),
                         "back_image": ("back.png", back_buf.getvalue(), "image/png")},
                  headers=headers)
assert r.status_code == 202, r.text
scan_id = r.json()["scan_id"]
print(f"[6] scan accepted: {scan_id}, polling...")

deadline = time.time() + 90
while True:
    r = requests.get(f"{BASE}/api/v1/scan/{scan_id}")
    body = r.json()
    if body.get("status") != "processing":
        break
    assert time.time() < deadline, "scan timed out"
    time.sleep(1)

assert body["status"] == "done", body
product = body["product"]
product_id = product["product_id"]
print(f"[7] scan done in poll loop. needs_review={body['needs_review']}, "
      f"ocr_confidence={body['ocr_confidence_avg']}")
print(f"    product: {product['product_name']} | category {product['category']} | "
      f"stars {product['inr']['rating_stars']}")

# --- 5. Product + compare + personalize ---------------------------------------------
r = requests.get(f"{BASE}/api/v1/product/{product_id}", headers=headers)
assert r.status_code == 200
print(f"[8] product fetched: {r.json()['product_name']}")

r = requests.post(f"{BASE}/api/v1/scan",
                  files={"front_image": ("front.png", front_buf.getvalue(), "image/png"),
                         "back_image": ("back.png", back_buf.getvalue(), "image/png")},
                  headers=headers)
scan_id_b = r.json()["scan_id"]
while requests.get(f"{BASE}/api/v1/scan/{scan_id_b}").json().get("status") == "processing":
    time.sleep(1)
product_b = requests.get(f"{BASE}/api/v1/scan/{scan_id_b}").json()["product"]["product_id"]

r = requests.post(f"{BASE}/api/v1/compare", json={
    "product_id_a": product_id, "product_id_b": product_b}, headers=headers)
assert r.status_code == 200, r.text
print("[9] compare OK:", {k: v["inr_stars"] for k, v in r.json().items()})

r = requests.post(f"{BASE}/api/v1/personalize", json={
    "product_id": product_id, "conditions": ["diabetes", "migraine", "fever", "sugar"]},
    headers=headers)
assert r.status_code == 200, r.text
for verdict in r.json()["verdicts"]:
    print(f"    [{verdict['condition']:>8}] {verdict['verdict']:<8} — {verdict['reasons'][0][:70]}")
print("    disclaimer:", r.json()["disclaimer"][:60], "...")

# --- 6. Compliance report ---------------------------------------------------------------
r = requests.get(f"{BASE}/api/v1/compliance-report/{product_id}/summary", headers=headers)
assert r.status_code == 200, r.text
summary = r.json()
print("[10] compliance summary:", summary["font_size_summary"], summary["declarations_summary"])

r = requests.get(f"{BASE}/api/v1/compliance-report/{product_id}", headers=headers)
assert r.status_code == 200
assert r.content[:5] == b"%PDF-"
open("/tmp/compliance_report.pdf", "wb").write(r.content)
print(f"[11] compliance PDF: {len(r.content)} bytes -> /tmp/compliance_report.pdf")

print("\nALL SMOKE TESTS PASSED ✔")
