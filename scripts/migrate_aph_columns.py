import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "..", "instance", "aicte_monitoring.db")
con = sqlite3.connect(db_path)
cur = con.cursor()
cur.execute("PRAGMA table_info(complaints)")
cols = [r[1] for r in cur.fetchall()]

if "potential_aph_clause" not in cols:
    cur.execute("ALTER TABLE complaints ADD COLUMN potential_aph_clause VARCHAR(100)")
    print("Added potential_aph_clause")
else:
    print("potential_aph_clause already exists")

if "aph_clause_status" not in cols:
    cur.execute("ALTER TABLE complaints ADD COLUMN aph_clause_status VARCHAR(50) DEFAULT 'Suggested'")
    print("Added aph_clause_status")
else:
    print("aph_clause_status already exists")

con.commit()
con.close()
print("Migration script executed successfully.")
