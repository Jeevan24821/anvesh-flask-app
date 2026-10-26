import io
import csv
import re
from datetime import datetime
import pytest
import pymupdf
from models.complaint import Complaint
from models.overlap import OverlapRelationship
from extensions import db


@pytest.fixture
def seeded_complaint_and_overlap(db_session, sample_institution, super_admin_user):
    c1 = Complaint(
        reference_number="AICTE-2026-CMP-9001",
        title="Unauthorized capitation fee demands in cash",
        description="Administration demanding Rs 50,000 cash for laboratory access.",
        institution_id=sample_institution.id,
        source_channel="Student grievance",
        category="Financial Issues and Fee Irregularities",
        priority="High",
        status="Open",
        created_at=datetime(2026, 10, 26, 16, 12, 0),
        resolution_date=None,
    )
    c2 = Complaint(
        reference_number="AICTE-2026-CMP-9002",
        title="Excess tuition fee hike without committee approval",
        description="Extortionate fee demanded under threat of examination debarment.",
        institution_id=sample_institution.id,
        source_channel="Student grievance",
        category="Financial Issues and Fee Irregularities",
        priority="High",
        status="Resolved",
        created_at=datetime(2026, 10, 25, 11, 30, 0),
        resolution_date=datetime(2026, 10, 26, 14, 0, 0),
    )
    db_session.add_all([c1, c2])
    db_session.commit()

    overlap = OverlapRelationship(
        first_complaint_id=c1.id,
        second_complaint_id=c2.id,
        similarity_score=0.88,
        semantic_score=0.82,
        keyword_score=0.75,
        category_score=1.0,
        context_score=0.5,
        relationship_type="Strong Potential Overlap",
        review_status="Pending Review",
        matching_evidence='{"shared_keywords": ["fee", "tuition", "cash"], "same_institution": true}',
        created_at=datetime(2026, 10, 26, 16, 15, 0),
        reviewed_at=None,
    )
    db_session.add(overlap)
    db_session.commit()

    return c1, c2, overlap


def test_search_actor_field_in_audit_log(client, super_admin_user):
    """Verifies that the Search Actor field in audit_log has proper labels, input, and contrast."""
    with client.session_transaction() as sess:
        sess["user_id"] = super_admin_user.id
        sess["username"] = super_admin_user.username
        sess["role"] = super_admin_user.role

    resp = client.get("/settings/audit-log")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Search Actor" in html
    assert 'name="actor"' in html
    assert 'placeholder="Search user name or role..."' in html
    assert "Immutable System Audit Log" in html


def test_source_channel_dropdown_excludes_other_for_new_entry(client, super_admin_user):
    """Verifies that 'Other' is removed from visible intake channel options in complaint form."""
    with client.session_transaction() as sess:
        sess["user_id"] = super_admin_user.id
        sess["username"] = super_admin_user.username
        sess["role"] = super_admin_user.role

    resp = client.get("/complaints/new")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Find the select id="source_channel" block
    select_match = re.search(r'<select[^>]*id="source_channel"[^>]*>(.*?)</select>', html, re.DOTALL)
    assert select_match is not None, "source_channel select element not found"
    select_inner = select_match.group(1)

    # 'Other' should NOT be an option in the select
    assert '<option value="Other"' not in select_inner
    # Legitimate channels must be present
    assert '<option value="Student grievance"' in select_inner or 'Student grievance' in select_inner
    assert '<option value="Institutional report"' in select_inner or 'Institutional report' in select_inner


def test_complaints_csv_export_dates_and_formatting(client, super_admin_user, seeded_complaint_and_overlap):
    """Verifies complaint CSV export date formatting (e.g. 26 Oct 2026, 16:12), Excel compatibility, and no ########."""
    with client.session_transaction() as sess:
        sess["user_id"] = super_admin_user.id
        sess["username"] = super_admin_user.username
        sess["role"] = super_admin_user.role

    resp = client.get("/reports/export/complaints.csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("Content-Type", "")

    raw_data = resp.data
    # Verify UTF-8 BOM
    assert raw_data.startswith(b"\xef\xbb\xbf")

    text_content = raw_data.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text_content))
    rows = list(reader)

    assert len(rows) > 1, "CSV should contain headers and rows"
    headers = rows[0]
    assert "Created At" in headers
    assert "Resolution Date" in headers

    created_idx = headers.index("Created At")
    res_idx = headers.index("Resolution Date")

    date_regex = re.compile(r"^\d{2} [A-Z][a-z]{2} \d{4}, \d{2}:\d{2}$")

    for row in rows[1:]:
        created_val = row[created_idx].lstrip("'")
        res_val = row[res_idx].lstrip("'")

        # Never literal ########
        assert "########" not in created_val
        assert "########" not in res_val

        # Created date must match standard date pattern
        assert date_regex.match(created_val), f"Created date '{created_val}' does not match expected format '26 Oct 2026, 16:12'"

        # Resolution date must either match format or be "Not recorded"
        assert res_val == "Not recorded" or date_regex.match(res_val), f"Resolution date '{res_val}' invalid"


def test_overlaps_csv_export_dates_and_formatting(client, super_admin_user, seeded_complaint_and_overlap):
    """Verifies overlap CSV export date formatting for Created At and Reviewed At."""
    with client.session_transaction() as sess:
        sess["user_id"] = super_admin_user.id
        sess["username"] = super_admin_user.username
        sess["role"] = super_admin_user.role

    resp = client.get("/reports/export/overlaps.csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("Content-Type", "")

    raw_data = resp.data
    assert raw_data.startswith(b"\xef\xbb\xbf")

    text_content = raw_data.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text_content))
    rows = list(reader)

    assert len(rows) > 1
    headers = rows[0]
    assert "Created At" in headers
    assert "Reviewed At" in headers

    created_idx = headers.index("Created At")
    reviewed_idx = headers.index("Reviewed At")

    date_regex = re.compile(r"^\d{2} [A-Z][a-z]{2} \d{4}, \d{2}:\d{2}$")

    for row in rows[1:]:
        created_val = row[created_idx].lstrip("'")
        reviewed_val = row[reviewed_idx].lstrip("'")

        assert "########" not in created_val
        assert "########" not in reviewed_val

        if created_val:
            assert date_regex.match(created_val), f"Created date '{created_val}' format error"

        # Reviewed At should be formatted date or "Not reviewed"
        assert reviewed_val == "Not reviewed" or date_regex.match(reviewed_val), f"Reviewed date '{reviewed_val}' format error"


def test_aicte_logo_acknowledgement_receipt_html_and_pdf(client, super_admin_user, seeded_complaint_and_overlap):
    """Verifies that the grievance acknowledgement receipt includes the centered official AICTE logo and real Code 128 barcode in HTML and PDF."""
    c1, _, _ = seeded_complaint_and_overlap
    with client.session_transaction() as sess:
        sess["user_id"] = super_admin_user.id
        sess["username"] = super_admin_user.username
        sess["role"] = super_admin_user.role

    # Test HTML view
    resp_html = client.get(f"/complaints/{c1.id}/receipt")
    assert resp_html.status_code == 200
    html_text = resp_html.get_data(as_text=True)

    assert "aicte_logo.png" in html_text
    assert "ALL INDIA COUNCIL FOR TECHNICAL EDUCATION" in html_text
    assert "Grievance Intake Acknowledgement Receipt" in html_text
    assert "data:image/png;base64," in html_text  # Real embedded Code 128 barcode data URI
    assert "VERIFIED AUTHENTIC" in html_text
    assert c1.reference_number in html_text

    # Test PDF download
    resp_pdf = client.get(f"/complaints/{c1.id}/receipt?download=pdf")
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers.get("Content-Type") == "application/pdf"
    assert f"attachment; filename=AICTE_Receipt_{c1.reference_number}.pdf" in resp_pdf.headers.get("Content-Disposition", "")

    pdf_bytes = resp_pdf.data
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 50000  # Genuine PDF with embedded image assets

    # Inspect PDF with PyMuPDF
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    assert len(doc) == 1
    page = doc[0]
    # Page must contain at least 2 images (the official AICTE logo AND the Code 128 barcode)
    images = page.get_images()
    assert len(images) >= 2, f"Generated PDF must contain both AICTE logo and Code 128 barcode, found {len(images)}"

    page_text = page.get_text()
    assert "ALL INDIA COUNCIL FOR TECHNICAL EDUCATION" in page_text
    assert "(Statutory Body under the Ministry of Education, Govt. of India)" in page_text
    assert "GRIEVANCE INTAKE ACKNOWLEDGEMENT RECEIPT" in page_text
    assert "GRIEVANCE REGISTRATION NUMBER (CASE ID)" in page_text
    assert c1.reference_number in page_text
    assert "VERIFIED AUTHENTIC" in page_text
    assert "ANVESH" in page_text
    assert "AUTHORIZED BUREAU HELPDESK & OFFICIAL COMMUNICATION DESK" in page_text


def test_institutional_queue_banner_contrast_and_elements(client, super_admin_user):
    """Verifies that the Institutional Review Queue banner has high contrast styling and typography."""
    with client.session_transaction() as sess:
        sess["user_id"] = super_admin_user.id
        sess["username"] = super_admin_user.username
        sess["role"] = super_admin_user.role

    resp = client.get("/queues/institutional")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)

    assert "queue-banner-warning" in text
    assert "queue-banner-title" in text
    assert "#0f2b48" in text  # High contrast deep navy
    assert "queue-banner-desc" in text
    assert "#334155" in text  # High contrast dark slate
    assert "#b45309" in text  # Dark amber icon
    assert "Institutional Reviewer Queue" in text


def test_overlap_explanation_grounded_evidence():
    """Verifies that overlap explainable_reason is strictly grounded in evidence and handles zero-evidence safely."""
    c1 = Complaint(id=9901, title="Lab issue", description="Test", category="Infrastructure", institution_id=10)
    c2 = Complaint(id=9902, title="Ragging issue", description="Other", category="Safety", institution_id=20)

    # 1. Zero evidence case
    o_zero = OverlapRelationship(
        first_complaint=c1,
        second_complaint=c2,
        similarity_score=0.1,
        semantic_score=0.0,
        keyword_score=0.0,
        category_score=0.0,
        context_score=0.0,
        matching_evidence='{"shared_keywords": [], "same_institution": false}',
    )

    reason_zero = o_zero.explainable_reason
    assert "No supporting detail available." in reason_zero
    assert "shared" not in reason_zero.lower()
    assert "narrative" not in reason_zero.lower()

    # 2. Genuine shared evidence case
    o_evidence = OverlapRelationship(
        first_complaint=c1,
        second_complaint=c2,
        similarity_score=0.85,
        semantic_score=0.82,
        keyword_score=0.75,
        category_score=0.9,
        context_score=0.5,
        matching_evidence='{"shared_keywords": ["capitation", "tuition"], "same_institution": true}',
    )

    reason_ev = o_evidence.explainable_reason
    assert "85" in reason_ev
    assert "shared domain terms" in reason_ev
    assert "capitation" in reason_ev
    assert "common technical institution campus" in reason_ev
