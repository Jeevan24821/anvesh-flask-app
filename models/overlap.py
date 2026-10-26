import json
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import relationship
from extensions import db


class OverlapRelationship(db.Base):
    """Potential or confirmed duplicate/overlap relationship between two complaints."""

    __tablename__ = "overlap_relationships"

    TYPES = [
        "Strong Potential Overlap",
        "Possible Overlap",
        "Human-Confirmed Related",
        "Human-Confirmed Not Related",
    ]

    REVIEW_STATUSES = ["Pending Review", "Confirmed Related", "Rejected Not Related"]

    id = Column(Integer, primary_key=True, autoincrement=True)
    first_complaint_id = Column(Integer, ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True)
    second_complaint_id = Column(Integer, ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True)
    similarity_score = Column(Float, nullable=False, index=True)
    semantic_score = Column(Float, nullable=False, default=0.0)
    keyword_score = Column(Float, nullable=False, default=0.0)
    category_score = Column(Float, nullable=False, default=0.0)
    context_score = Column(Float, nullable=False, default=0.0)
    relationship_type = Column(String(50), nullable=False, default="Possible Overlap", index=True)
    review_status = Column(String(50), nullable=False, default="Pending Review", index=True)
    matching_evidence = Column(Text, nullable=False)
    conflicting_evidence = Column(Text, nullable=True)
    algorithm_version = Column(String(100), nullable=False, default="v2.0-hybrid")
    reviewer_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at = Column(DateTime, nullable=True)

    # Ensure canonical ordering and prevent duplicate pairs
    __table_args__ = (
        UniqueConstraint("first_complaint_id", "second_complaint_id", name="uq_complaint_pair"),
        CheckConstraint("first_complaint_id < second_complaint_id", name="ck_canonical_pair_order"),
    )

    # Relationships
    first_complaint = relationship("Complaint", foreign_keys=[first_complaint_id], back_populates="overlaps_as_first")
    second_complaint = relationship("Complaint", foreign_keys=[second_complaint_id], back_populates="overlaps_as_second")
    reviewer = relationship("User", back_populates="reviewed_overlaps")

    @property
    def evidence_data(self):
        try:
            data = json.loads(self.matching_evidence)
            if isinstance(data, list):
                extracted_kws = []
                for item in data:
                    if "Common keywords:" in item:
                        kws_str = item.split("Common keywords:", 1)[1]
                        extracted_kws.extend([k.strip().lower() for k in kws_str.split(",") if k.strip()])
                return {
                    "summary": " ".join(data),
                    "shared_keywords": extracted_kws,
                    "legacy_reasons": data,
                }
            elif isinstance(data, dict):
                return data
            return {"summary": str(data), "shared_keywords": []}
        except Exception:
            return {"summary": self.matching_evidence, "shared_keywords": [], "explanation": self.matching_evidence}

    def _ensure_computed_signals(self):
        """Ensures genuine component signals are calculated if stored scores are zero or missing."""
        if hasattr(self, "_computed_signals_cache"):
            return self._computed_signals_cache

        sem = self.semantic_score if self.semantic_score and self.semantic_score > 0 else 0.0
        kw = self.keyword_score if self.keyword_score and self.keyword_score > 0 else 0.0
        cat = self.category_score if self.category_score and self.category_score > 0 else 0.0
        ctx = self.context_score if self.context_score and self.context_score > 0 else 0.0
        shared_kws = (self.evidence_data or {}).get("shared_keywords") or []

        if (sem == 0.0 and kw == 0.0 and cat == 0.0) and self.first_complaint and self.second_complaint:
            try:
                from services.overlap_detection import (
                    compute_semantic_similarity,
                    compute_keyword_similarity,
                    compute_category_compatibility,
                    compute_context_similarity,
                    extract_facilities,
                )
                from services.categorization import extract_keywords

                c1 = self.first_complaint
                c2 = self.second_complaint
                t1 = f"{c1.title or ''}. {c1.description or ''}"
                t2 = f"{c2.title or ''}. {c2.description or ''}"

                sem, _ = compute_semantic_similarity(t1, t2, allow_transformer=False)
                kw1 = extract_keywords(t1, top_k=8)
                kw2 = extract_keywords(t2, top_k=8)
                kw, dynamic_kws = compute_keyword_similarity(kw1, kw2)
                cat = compute_category_compatibility(c1.category, c2.category)
                fac1 = extract_facilities(t1)
                fac2 = extract_facilities(t2)
                ctx, ctx_details = compute_context_similarity(c1, c2, fac1, fac2)
                if not shared_kws and dynamic_kws:
                    shared_kws = dynamic_kws
            except Exception:
                pass

        self._computed_signals_cache = {
            "semantic_score": sem,
            "keyword_score": kw,
            "category_score": cat,
            "context_score": ctx,
            "shared_keywords": shared_kws,
        }
        return self._computed_signals_cache

    @property
    def effective_semantic_score(self) -> float:
        if self.semantic_score and self.semantic_score > 0:
            return self.semantic_score
        return self._ensure_computed_signals()["semantic_score"]

    @property
    def effective_keyword_score(self) -> float:
        if self.keyword_score and self.keyword_score > 0:
            return self.keyword_score
        return self._ensure_computed_signals()["keyword_score"]

    @property
    def effective_category_score(self) -> float:
        if self.category_score and self.category_score > 0:
            return self.category_score
        return self._ensure_computed_signals()["category_score"]

    @property
    def effective_context_score(self) -> float:
        if self.context_score and self.context_score > 0:
            return self.context_score
        return self._ensure_computed_signals()["context_score"]

    @property
    def effective_shared_keywords(self) -> list:
        ev_kws = (self.evidence_data or {}).get("shared_keywords") or []
        if ev_kws:
            return ev_kws
        return self._ensure_computed_signals()["shared_keywords"]

    @property
    def explainable_reason(self) -> str:
        """Returns a concise, evidence-grounded explanation derived strictly from genuine signals."""
        c1 = self.first_complaint
        c2 = self.second_complaint
        if not c1 or not c2:
            return "No supporting detail available."

        sim = self.similarity_score or 0.0
        sem = self.effective_semantic_score
        kw = self.effective_keyword_score
        cat = self.effective_category_score
        shared_kws = self.effective_shared_keywords
        same_inst = (c1.institution_id == c2.institution_id) or (self.evidence_data or {}).get("same_institution", False)

        # Zero or sub-threshold evidence check
        if sim < 0.25 and not shared_kws:
            return "No supporting detail available."

        parts = []
        sim_pct = round(sim * 100, 1)

        # Topic detection
        t1 = f"{c1.title or ''}. {c1.description or ''}".lower()
        t2 = f"{c2.title or ''}. {c2.description or ''}".lower()
        topic = None
        if "fee" in t1 and "fee" in t2:
            topic = "fee structure and tuition charges"
        elif "ragging" in t1 or "harassment" in t1:
            topic = "harassment and campus discipline"
        elif "curriculum" in t1 or "internship" in t1:
            topic = "academic curriculum and internship mandates"
        elif "lab" in t1 or "equipment" in t1:
            topic = "laboratory infrastructure and equipment deficit"
        elif "water" in t1 or "sanitation" in t1:
            topic = "campus sanitation and student amenities"
        elif "admission" in t1 or "intake" in t1:
            topic = "unapproved student intake capacity"

        # 1. Similarity summary & narrative text alignment
        if sem is not None and sem >= 0.80:
            if topic:
                parts.append(f"AI overlap engine detected {sim_pct}% composite match: complaints report the same {topic} with nearly identical narrative text ({round(sem * 100, 1)}% phrasing alignment)")
            else:
                parts.append(f"AI overlap engine detected {sim_pct}% composite match with matching grievance text ({round(sem * 100, 1)}% phrasing alignment)")
        elif sem is not None and sem >= 0.35:
            if topic:
                parts.append(f"AI overlap engine detected {sim_pct}% composite match: grievances describe related aspects of {topic} ({round(sem * 100, 1)}% text alignment)")
            else:
                parts.append(f"AI overlap engine detected {sim_pct}% composite match with {round(sem * 100, 1)}% text alignment")
        else:
            if topic:
                parts.append(f"AI overlap engine flagged {sim_pct}% composite match concerning {topic}")
            else:
                parts.append(f"AI overlap engine flagged {sim_pct}% composite match between these records")

        # 2. Shared domain terms
        if shared_kws:
            kw_sample = ", ".join(f"'{k}'" for k in shared_kws[:5])
            parts.append(f"identified shared domain terms: {kw_sample}")

        # 3. Category match
        if c1.category and c2.category:
            if c1.category.lower() == c2.category.lower():
                parts.append(f"both filed under grievance category '{c1.category}'")
            elif cat and cat >= 0.40:
                parts.append(f"categories '{c1.category}' and '{c2.category}' are taxonomically compatible")

        rationale = "; ".join(parts) + "."

        # 4. Campus / Institution connection
        if same_inst:
            inst_name = c1.institution.name if c1.institution else "the campus"
            rationale += f" Both grievances target the common technical institution campus ({inst_name})."
        elif c1.institution_id and c2.institution_id and c1.institution_id != c2.institution_id:
            name1 = c1.institution.name if c1.institution else "Institution A"
            name2 = c2.institution.name if c2.institution else "Institution B"
            rationale += f" Filed across different institutions ({name1} vs {name2}), indicating an inter-institutional regulatory pattern."

        return rationale

    def to_dict(self):
        return {
            "id": self.id,
            "first_complaint_id": self.first_complaint_id,
            "first_complaint_ref": self.first_complaint.reference_number if self.first_complaint else None,
            "first_complaint_title": self.first_complaint.title if self.first_complaint else None,
            "second_complaint_id": self.second_complaint_id,
            "second_complaint_ref": self.second_complaint.reference_number if self.second_complaint else None,
            "second_complaint_title": self.second_complaint.title if self.second_complaint else None,
            "institution_name": self.first_complaint.institution.name if self.first_complaint and self.first_complaint.institution else None,
            "same_institution": (self.first_complaint.institution_id == self.second_complaint.institution_id) if (self.first_complaint and self.second_complaint) else False,
            "similarity_score": round(self.similarity_score, 4),
            "similarity_percentage": round(self.similarity_score * 100, 1),
            "semantic_score": round(self.semantic_score, 4),
            "keyword_score": round(self.keyword_score, 4),
            "category_score": round(self.category_score, 4),
            "context_score": round(self.context_score, 4),
            "relationship_type": self.relationship_type,
            "review_status": self.review_status,
            "explainable_reason": self.explainable_reason,
            "evidence": self.evidence_data,
            "conflicting_evidence": self.conflicting_evidence,
            "algorithm_version": self.algorithm_version,
            "reviewer_name": self.reviewer.display_name if self.reviewer else None,
            "review_notes": self.review_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }

    def __repr__(self):
        return f"<OverlapRelationship {self.first_complaint_id}<->{self.second_complaint_id}: {self.similarity_score:.2f} ({self.review_status})>"
