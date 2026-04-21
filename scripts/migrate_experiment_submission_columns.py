from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "data" / "app.db"

conn = sqlite3.connect(str(DB_PATH))
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE experiment_submissions ADD COLUMN question_started_at DATETIME")
    print("Added question_started_at")
except Exception as e:
    print("question_started_at maybe already exists:", e)

try:
    cur.execute("ALTER TABLE experiment_submissions ADD COLUMN answer_deadline_at DATETIME")
    print("Added answer_deadline_at")
except Exception as e:
    print("answer_deadline_at maybe already exists:", e)

conn.commit()
conn.close()
print("done")