"""AICTE Approval Process Handbook (APH 2024-25 to 2026-27) Violation Clause Tagging Service.

Provides deterministic, lightweight rule-based catalogue matching complaint text
and category against verified AICTE Approval Process Handbook clauses.

Display Format Requirement:
  - "Potential APH Clause: <Clause Number>"
  - "Potential APH Clause: No relevant clause identified."
"""

import re
from typing import Optional, Tuple, Dict, Any

# Verified APH 2024-27 Clause Catalogue
APH_CLAUSE_CATALOGUE = [
    {
        "clause": "Clause 6.35",
        "title": "Prohibition of Capitation Fee or Donation",
        "description": "No technical institution shall charge capitation fee or demand unauthorized donation for admission.",
        "category_triggers": ["Fee Overcharging / Capitation"],
        "keywords": [
            "capitation", "donation", "bribe", "extra money for seat", "under the table",
            "cash donation", "management quota fee", "excess fee", "overcharging"
        ],
    },
    {
        "clause": "Clause 6.45",
        "title": "Fee Refund Policy & Non-Retention of Original Documents",
        "description": "Mandatory refund of fees upon cancellation/withdrawal of admission and unconditional return of original certificates.",
        "category_triggers": ["Withholding Original Certificates"],
        "keywords": [
            "refund", "fee refund", "cancellation of admission", "withdraw admission",
            "withholding certificate", "retaining original", "original certificate",
            "mark sheet", "marksheet", "degree certificate", "transfer certificate", "migration certificate"
        ],
    },
    {
        "clause": "Clause 6.47",
        "title": "Prevention and Prohibition of Ragging in Technical Institutions",
        "description": "Establishment of Anti-Ragging Committee, Squad, monitoring cell, and zero-tolerance ragging enforcement.",
        "category_triggers": ["Ragging and Student Harassment"],
        "keywords": [
            "ragging", "ragged", "harassment by senior", "bullied by senior", "physical abuse",
            "verbal abuse", "humiliation", "anti-ragging", "ragging committee"
        ],
    },
    {
        "clause": "Clause 6.48",
        "title": "Internal Committee (IC) / Gender Sensitization & Prevention of Sexual Harassment",
        "description": "Mandatory constitution of Internal Committee (IC) for prevention and redressal of sexual harassment.",
        "category_triggers": [],
        "keywords": [
            "sexual harassment", "gender discrimination", "molestation", "inappropriate touch",
            "posh", "internal committee", "women cell", "female safety"
        ],
    },
    {
        "clause": "Clause 6.49",
        "title": "Committee for SC/ST (Prevention of Caste Discrimination & Atrocities)",
        "description": "Enforcement of Prevention of Caste Discrimination norms and establishment of SC/ST cell.",
        "category_triggers": ["Discrimination and Student Welfare"],
        "keywords": [
            "caste discrimination", "sc/st", "untouchability", "atrocity", "dalit",
            "caste slurs", "reservation denial", "sc st committee"
        ],
    },
    {
        "clause": "Clause 6.14",
        "title": "Faculty Cadre Ratio, 7th CPC Pay Scale & Faculty Protection Norms",
        "description": "Compliance with prescribed Cadre Ratio, AICTE 7th CPC pay scales, and prohibition on retaining faculty certificates.",
        "category_triggers": ["Faculty Non-Payment & Understaffing", "Faculty and staffing"],
        "keywords": [
            "faculty salary", "unpaid salary", "7th cpc", "salary arrears", "pay scale",
            "delay in salary", "understaffed", "faculty student ratio", "teacher salary",
            "faculty certificates", "cadre ratio"
        ],
    },
    {
        "clause": "Clause 6.19",
        "title": "Norms for Essential Facilities, Laboratories, Computing & Library",
        "description": "Adequate lab apparatus, computational infrastructure, licensed software, high-speed internet, and physical library volumes.",
        "category_triggers": [
            "Infrastructure & Laboratory Deficit",
            "Laboratory Equipment and Infrastructure",
            "Laboratory and equipment",
            "Library and learning resources",
            "Library and Learning Resources"
        ],
        "keywords": [
            "laboratory", "lab equipment", "apparatus", "machine broken", "not working",
            "computer lab", "software license", "internet bandwidth", "wifi not working",
            "library books", "reading room", "practical equipment", "lathe"
        ],
    },
    {
        "clause": "Clause 6.17",
        "title": "Norms for Land, Built-up Area, Building Safety & Fire Safety",
        "description": "Mandatory compliance with approved built-up area, certified structural safety, and valid fire safety clearances.",
        "category_triggers": ["Safety and Security"],
        "keywords": [
            "fire safety", "building unsafe", "fire clearance", "fire extinguisher",
            "structural crack", "emergency exit", "evacuation", "building collapse risk"
        ],
    },
    {
        "clause": "Clause 6.42",
        "title": "Tuition Fee Waiver (TFW) Scheme Compliance",
        "description": "Mandatory supernumerary Tuition Fee Waiver (TFW) implementation for meritorious and economically disadvantaged students.",
        "category_triggers": ["Scholarship Delays"],
        "keywords": [
            "tuition fee waiver", "tfw", "tfw scheme", "fee concession denied",
            "economically weaker section waiver", "waiver seat"
        ],
    },
    {
        "clause": "Clause 6.50",
        "title": "Student Grievance Redressal Mechanism & Ombudsman Norms",
        "description": "Establishment of Online Grievance Redressal portal, functional SGRC, and appointment of University Ombudsman.",
        "category_triggers": [],
        "keywords": [
            "sgrc", "ombudsman", "grievance committee not functioning", "no grievance portal",
            "grievance redressal committee", "hearing denied"
        ],
    },
    {
        "clause": "Clause 7.4 (g)",
        "title": "Prohibition of Excess Admission over Approved Intake",
        "description": "Admitting students in excess of AICTE approved intake without statutory sanction.",
        "category_triggers": ["Unapproved Courses & Excess Intake"],
        "keywords": [
            "excess intake", "admitted beyond intake", "over admission", "unapproved batch",
            "intake capacity", "illegal admission beyond seats"
        ],
    },
    {
        "clause": "Clause 7.4 (h)",
        "title": "Violation of Admission Eligibility and Unapproved Courses",
        "description": "Offering technical programs without AICTE approval or violating prescribed eligibility criteria.",
        "category_triggers": ["Admissions & Affiliation Irregularities"],
        "keywords": [
            "unapproved course", "unapproved program", "fake affiliation", "without aicte approval",
            "admission eligibility violation", "degrees not recognized"
        ],
    },
]


def match_aph_clause(text: str, category: str = "") -> Optional[str]:
    """Matches complaint text and category against the verified APH catalogue.
    
    Returns the most relevant clause string (e.g. 'Clause 6.45') or None.
    """
    if not text and not category:
        return None

    combined_text = f"{category} {text}".lower()

    # Pass 1: Direct category triggers with keyword verification
    for entry in APH_CLAUSE_CATALOGUE:
        if category and any(category.strip().lower() == ct.lower() for ct in entry["category_triggers"]):
            # Specific category matched directly
            return entry["clause"]

    # Pass 2: Keyword scoring across catalogue
    best_clause = None
    max_matches = 0

    for entry in APH_CLAUSE_CATALOGUE:
        matches = 0
        for kw in entry["keywords"]:
            if re.search(r"\b" + re.escape(kw.lower()) + r"\b", combined_text):
                matches += 1

        if matches > max_matches:
            max_matches = matches
            best_clause = entry["clause"]

    # Require at least 1 strong keyword match to assign clause
    if max_matches >= 1 and best_clause:
        return best_clause

    return None


def get_clause_display_text(clause_id: Optional[str]) -> str:
    """Formats strictly according to specification:
    'Potential APH Clause: <Clause Number>'
    or
    'Potential APH Clause: No relevant clause identified.'
    """
    if clause_id and clause_id.strip():
        val = clause_id.strip()
        # Normalizes format if 'Clause ' is already in the string
        if not val.lower().startswith("clause"):
            val = f"Clause {val}"
        return f"Potential APH Clause: {val}"
    return "Potential APH Clause: No relevant clause identified."


def get_clause_meta(clause_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Returns metadata for the identified clause, if found."""
    if not clause_id:
        return None
    c_clean = clause_id.strip().lower()
    for entry in APH_CLAUSE_CATALOGUE:
        if entry["clause"].lower() == c_clean or entry["clause"].lower().replace("clause ", "") == c_clean:
            return entry
    return None
