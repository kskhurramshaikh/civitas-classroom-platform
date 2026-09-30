"""
CLI entrypoint for seeding one school, one teacher (Ms. Sama), one
class, a handful of students (including Zayan and Ibrahim from the
pitch prototype), the six developmental domains used in the Learning
Garden parent app, and one parent account per student — so the API has
something real to query immediately after first deploy.

The actual seeding logic lives in app/services/seed.py (shared with
the /admin/seed-demo endpoint, for environments like Render's free
plan that have no Shell access to run this script directly).

Run with:  python -m scripts.seed_demo
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.services.seed import seed


def run():
    db = SessionLocal()
    try:
        seeded = seed(db)
        if seeded:
            print("Seeded: school, teacher (sama@civitas.edu.pk), class, 2 students + parents.")
            print("All demo passwords: changeme123")
        else:
            print("Skipped: a 'Civitas' school already exists in this database.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
