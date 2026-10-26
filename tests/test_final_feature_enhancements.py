import pytest
from app import create_app
from extensions import db
from models.user import User
from models.institution import Institution
from models.complaint import Complaint
from models.overlap import OverlapRelationship
from services.aph_clause_service import match_aph_clause, get_clause_display_text, get_clause_meta


@pytest.fixture
def app_instance():
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        yield app


@pytest.fixture
def client(app_instance):
    return app_instance.test_client()


# ==============================================================================
# FEATURE A TESTS: EXPLAINABLE AI OVERLAP INSIGHTS
# ==============================================================================

def test_explainable_ai_overlap_signals_and_reason(app_instance):
    """Verifies that OverlapRelationship exposes genuine signals and plain-English reasons."""
    with app_instance.app_context():
        overlap = db.session.query(OverlapRelationship).first()
        assert overlap is not None, "Overlap relationships must exist in the database."

        # 1. Genuine similarity score and percentage
        assert 0.0 <= overlap.similarity_score <= 1.0
        pct = round(overlap.similarity_score * 100, 1)
        assert pct > 0

        # 2. Plain-English explainable reason
        reason = overlap.explainable_reason
        assert isinstance(reason, str) and len(reason) > 10
        assert f"{pct}%" in reason or "overlap" in reason.lower()

        # 3. Matching signals in evidence
        ev = overlap.evidence_data
        assert "summary" in ev
        assert "shared_keywords" in ev
        assert "breakdown" in ev or hasattr(overlap, "semantic_score")

        # 4. to_dict includes explainable_reason
        d = overlap.to_dict()
        assert "explainable_reason" in d
        assert "similarity_percentage" in d
        assert d["similarity_percentage"] == pct


def test_overlap_review_adjudication_preserves_records(client, app_instance):
    """Verifies that authorized reviewers can confirm/reject overlap relationships without deleting records."""
    with app_instance.app_context():
        overlap = db.session.query(OverlapRelationship).filter_by(review_status="Pending Review").first()
        if not overlap:
            overlap = db.session.query(OverlapRelationship).first()

        cid1 = overlap.first_complaint_id
        cid2 = overlap.second_complaint_id

        # Log in as central officer
        with client.session_transaction() as sess:
            admin_user = db.session.query(User).filter_by(username="admin").first()
            sess["user_id"] = admin_user.id
            sess["role"] = admin_user.role

        # Action 1: Confirm Related
        res = client.post(f"/overlaps/{overlap.id}/review", data={"action": "confirm", "notes": "Verified match."}, follow_redirects=True)
        assert res.status_code == 200

        # Check overlap updated
        updated_ov = db.session.query(OverlapRelationship).get(overlap.id)
        assert updated_ov.review_status == "Confirmed Related"

        # Check complaints are preserved (not deleted or auto-merged)
        c1 = db.session.query(Complaint).get(cid1)
        c2 = db.session.query(Complaint).get(cid2)
        assert c1 is not None
        assert c2 is not None

        # Action 2: Reset to Pending
        res2 = client.post(f"/overlaps/{overlap.id}/review", data={"action": "reset"}, follow_redirects=True)
        assert res2.status_code == 200
        db.session.refresh(updated_ov)
        assert updated_ov.review_status == "Pending Review"


# ==============================================================================
# FEATURE B TESTS: APH VIOLATION CLAUSE TAGGING
# ==============================================================================

def test_aph_clause_matching_catalogue():
    """Verifies deterministic catalogue matching against AICTE APH clauses."""
    # 1. Fee refund / documents
    c_refund = match_aph_clause("College refuses to refund my admission fee after withdrawal and is retaining original certificates")
    assert c_refund == "Clause 6.45"

    # 2. Capitation / donations
    c_capitation = match_aph_clause("Demanded donation of 5 lakhs for admission seat under management quota")
    assert c_capitation == "Clause 6.35"

    # 3. Ragging
    c_ragging = match_aph_clause("Severe ragging and physical abuse by senior students in hostel")
    assert c_ragging == "Clause 6.47"

    # 4. Faculty salary / understaffing
    c_faculty = match_aph_clause("Professors have unpaid salary for 6 months violating 7th cpc norms")
    assert c_faculty == "Clause 6.14"

    # 5. Laboratory equipment
    c_lab = match_aph_clause("Laboratory apparatus broken and computer lab has no internet")
    assert c_lab == "Clause 6.19"

    # 6. Negative match (no relevant clause)
    c_none = match_aph_clause("The college garden has dry grass and the bench is painted blue.")
    assert c_none is None


def test_aph_clause_strict_display_format():
    """Verifies display strictly follows:
    'Potential APH Clause: <Clause Number>' or 'Potential APH Clause: No relevant clause identified.'
    """
    # Positive
    display_pos = get_clause_display_text("Clause 6.45")
    assert display_pos == "Potential APH Clause: Clause 6.45"

    display_num = get_clause_display_text("6.35")
    assert display_num == "Potential APH Clause: Clause 6.35"

    # Negative
    display_neg = get_clause_display_text(None)
    assert display_neg == "Potential APH Clause: No relevant clause identified."

    display_empty = get_clause_display_text("")
    assert display_empty == "Potential APH Clause: No relevant clause identified."


def test_complaint_aph_clause_property_and_decision(client, app_instance):
    """Verifies Complaint model property and reviewer confirmation / rejection route."""
    with app_instance.app_context():
        complaint = db.session.query(Complaint).first()
        assert complaint is not None

        # Check property output adheres to strict format
        display = complaint.aph_clause_display
        assert display.startswith("Potential APH Clause:")
        assert ("Clause" in display or "No relevant clause identified." in display)

        # Log in as reviewer
        with client.session_transaction() as sess:
            admin_user = db.session.query(User).filter_by(username="admin").first()
            sess["user_id"] = admin_user.id
            sess["role"] = admin_user.role

        # Reviewer action: confirm clause
        res = client.post(
            f"/complaints/{complaint.id}/aph-clause-decision",
            data={"action": "confirm", "clause": "Clause 6.19"},
            follow_redirects=True,
        )
        assert res.status_code == 200

        db.session.refresh(complaint)
        assert complaint.aph_clause_status == "Confirmed"
        assert complaint.potential_aph_clause == "Clause 6.19"
        assert complaint.aph_clause_display == "Potential APH Clause: Clause 6.19"

        # Reviewer action: reject clause
        res2 = client.post(
            f"/complaints/{complaint.id}/aph-clause-decision",
            data={"action": "reject"},
            follow_redirects=True,
        )
        assert res2.status_code == 200
        db.session.refresh(complaint)
        assert complaint.aph_clause_status == "Rejected"
        assert complaint.potential_aph_clause is None


# ==============================================================================
# LOGIN & ACCOUNT SCREEN TESTS
# ==============================================================================

def test_student_password_login(client, app_instance):
    """Verifies that students can log in directly using USN and password without OTP."""
    res = client.post(
        "/login",
        data={
            "portal": "student",
            "login_type": "password",
            "identifier": "1DS22CS089",
            "password": "StudentPass123",
        },
        follow_redirects=False,
    )
    # Should redirect to student portal (/student/complaints)
    assert res.status_code == 302
    assert "/student" in res.headers.get("Location", "")


def test_parent_password_login(client, app_instance):
    """Verifies that parents can log in using Parent ID and password."""
    res = client.post(
        "/login",
        data={
            "portal": "parent",
            "login_type": "password",
            "identifier": "PAR-984501",
            "password": "Demo@123",
        },
        follow_redirects=False,
    )
    # Should redirect to student/ward complaints portal
    assert res.status_code == 302
    assert "/student" in res.headers.get("Location", "")


def test_faculty_role_login_and_permission_isolation(client, app_instance):
    """Verifies that Faculty logs into Portal B (institution) without gaining AICTE Central administrative rights."""
    res = client.post(
        "/login",
        data={
            "portal": "institution",
            "login_type": "password",
            "username": "inst_admin",
            "password": "InstPass123",
        },
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "/dashboard" in res.headers.get("Location", "")

    # Now verify with logged in session that Faculty does NOT have super_admin rights
    with app_instance.app_context():
        faculty_user = db.session.query(User).filter_by(username="inst_admin").first()
        assert faculty_user.is_institutional_reviewer is True
        assert faculty_user.is_super_admin is False
        assert faculty_user.is_aicte_officer is False


def test_login_labels_and_sidebar_items_removal(client):
    """Verifies that 'Login' label is present, and Inspect Queue & Advisory card are removed from sidebar."""
    # Check login page
    res_login = client.get("/login")
    assert res_login.status_code == 200
    html = res_login.get_data(as_text=True)

    assert "Login" in html
    assert "Login as Student" in html
    assert "Login as Faculty" in html
    assert "Login as Parent / Guardian" in html
    assert "Sign In to Regulatory Console" not in html

    # Check dashboard sidebar with admin session
    with client.session_transaction() as sess:
        sess["user_id"] = 3
        sess["username"] = "admin"
        sess["role"] = "aicte_officer"

    res_dash = client.get("/dashboard")
    assert res_dash.status_code == 200
    dash_html = res_dash.get_data(as_text=True)

    # UI items removed from sidebar as requested in prompt
    assert "Inspect Queue" not in dash_html
    assert "AICTE Advisory" not in dash_html
    assert "Overlap Intelligence" in dash_html

    # But underlying route remains fully operational
    res_queue = client.get("/overlaps?status=Pending+Review")
    assert res_queue.status_code == 200
