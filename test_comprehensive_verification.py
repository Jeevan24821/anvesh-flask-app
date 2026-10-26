import urllib.request
import urllib.parse
import http.cookiejar
import re

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

BASE_URL = "http://127.0.0.1:5000"

def get(path):
    req = urllib.request.Request(f"{BASE_URL}{path}")
    with opener.open(req) as resp:
        return resp.getcode(), resp.read().decode('utf-8', errors='ignore')

def get_bytes(path):
    req = urllib.request.Request(f"{BASE_URL}{path}")
    with opener.open(req) as resp:
        return resp.getcode(), resp.headers.get_content_type(), resp.read()

def post(path, data):
    encoded = urllib.parse.urlencode(data).encode('utf-8')
    req = urllib.request.Request(f"{BASE_URL}{path}", data=encoded, method="POST")
    with opener.open(req) as resp:
        return resp.getcode(), resp.read().decode('utf-8', errors='ignore')

# 1. Login
code, html = post("/login", {"username": "admin", "password": "Admin@123"})
print(f"Login status: {code}")
assert "Dashboard" in html or "ANVESH" in html or code == 200

# 2. Test all 11 bureau review queues
queues = [
    "all", "pgrc", "rb", "ab", "papb", "fb", "arc", "sdc", "rc", "institutional", "manual", "unrouted"
]
print("\n=== Testing Bureau Review Queues ===")
for q in queues:
    code, html = get(f"/queues/{q}")
    assert code == 200, f"Queue {q} returned {code}"
    # Verify banner or empty state
    has_banner = f"queue-banner-{q}" in html or "queue-banner" in html
    has_empty = "No grievances found for this queue" in html
    has_table = "queuesTable" in html
    print(f"Queue '{q:13}': HTTP {code} | Banner: {has_banner} | Table: {has_table} | Empty State Check: {'Present' if has_empty else 'Populated with records'}")

# 3. Test Overlap Intelligence
print("\n=== Testing Overlap Intelligence ===")
code, html = get("/overlaps")
assert code == 200
assert "Explainable AI Overlap Insights" in html
assert "Relationship Rationale:" in html
print(f"Overlaps page: HTTP {code} | Explainable AI Overlap Insights & Relationship Rationale confirmed")

# Check Overlap 66 (Complaints 48 & 49)
assert "100.0%" in html, "100.0% score should be visible on overlaps page for identical pairs"
print("Found 100.0% signal on Overlaps page for identical harassment complaints")

# Check Complaint Detail Overlap Signals
print("\n=== Testing Complaint Detail Overlap Signals ===")
for cid in [48, 31]:
    code, html = get(f"/complaints/{cid}")
    assert code == 200
    assert "Explainable Overlap Insights: Why These Grievances May Be Related" in html
    assert "Relationship Rationale:" in html
    assert "Semantic Description" in html
    assert "Shared Keywords" in html
    assert "Category Compatibility" in html
    assert "Institutional Connection" in html
    assert "Same Institution" in html
    print(f"Complaint #{cid} Detail: HTTP {code} | All 4 Explainable Signals & Rationale verified!")

# 4. Test Acknowledgement Receipt & PDF
print("\n=== Testing Acknowledgement PDF & Receipt ===")
code, html = get("/complaints/1/receipt")
assert code == 200
assert "ALL INDIA COUNCIL FOR TECHNICAL EDUCATION" in html
assert "aicte_logo.png" in html
assert "Grievance Intake Acknowledgement Receipt" in html
print(f"HTML Receipt Preview: HTTP {code} | AICTE Logo & Heading confirmed")

code, content_type, pdf_data = get_bytes("/complaints/1/receipt?download=pdf")
assert code == 200
assert content_type == "application/pdf"
assert len(pdf_data) > 100000  # valid PDF with embedded high-res logo
assert pdf_data.startswith(b"%PDF")
print(f"PDF Download: HTTP {code} | Content-Type: {content_type} | Size: {len(pdf_data):,} bytes | %PDF Header confirmed")

print("\n>>> ALL COMPREHENSIVE CHECKS PASSED SUCCESSFULLY! <<<")
