"""
normalize.py - convert the HW5 schema to 3rd normal form and move the data.

  1. CREATE the 3NF tables + view   (schema_3nf.sql, idempotent)
  2. if `request` is not already a complete copy of `requests`:
       empty request / client_ip / country, then run migrate_3nf.sql in one transaction
  3. run the checks in check_3nf.sql and print them

usage: python3 normalize.py --instance PROJECT:REGION:INSTANCE [--force]
"""
import argparse

import sqlalchemy

import db
from sqlrun import show, statements


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="cedar-pottery-508921-u1")
    ap.add_argument("--instance", default="cedar-pottery-508921-u1:us-central1:hw5-db")
    ap.add_argument("--db-name", default="hw5")
    ap.add_argument("--db-user", default="hw5app")
    ap.add_argument("--db-secret", default="hw5-db-password")
    ap.add_argument("--force", action="store_true", help="re-run the migration even if done")
    ap.add_argument("--db-url", help="testing only: SQLAlchemy URL instead of Cloud SQL")
    a = ap.parse_args()
    engine = (sqlalchemy.create_engine(a.db_url) if a.db_url else
              db.make_engine(a.instance, a.db_user, db.get_password(a.project, a.db_secret),
                             a.db_name, pool_size=1))

    print("== creating 3NF schema (schema_3nf.sql)", flush=True)
    with engine.begin() as c:
        for s in statements("schema_3nf.sql"):
            c.execute(sqlalchemy.text(s))

    with engine.connect() as c:
        old = c.execute(sqlalchemy.text("SELECT COUNT(*) FROM requests")).scalar()
        new = c.execute(sqlalchemy.text("SELECT COUNT(*) FROM request")).scalar()
    if new == old and old > 0 and not a.force:
        print(f"== data already migrated ({new} rows) - skipping migrate_3nf.sql", flush=True)
    else:
        print(f"== migrating {old} rows (migrate_3nf.sql)", flush=True)
        with engine.begin() as c:
            for t in ("request", "client_ip", "country"):
                c.execute(sqlalchemy.text(f"DELETE FROM {t}"))
            for s in statements("migrate_3nf.sql"):
                c.execute(sqlalchemy.text(s))

    print("== checks (check_3nf.sql)", flush=True)
    with engine.connect() as c:
        for s in statements("check_3nf.sql"):
            show(c, s)


if __name__ == "__main__":
    main()
