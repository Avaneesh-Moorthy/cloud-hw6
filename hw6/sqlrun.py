"""sqlrun.py - small helpers: split a .sql file into statements and print query results."""
import os

import sqlalchemy

HERE = os.path.dirname(os.path.abspath(__file__))


def statements(filename):
    text = open(os.path.join(HERE, filename)).read()
    lines = [l for l in text.splitlines() if not l.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def show(conn, sql):
    res = conn.execute(sqlalchemy.text(sql))
    cols = list(res.keys())
    rows = [["" if v is None else str(v) for v in r] for r in res]
    w = [max([len(c)] + [len(r[i]) for r in rows]) for i, c in enumerate(cols)]
    line = "+" + "+".join("-" * (x + 2) for x in w) + "+"
    out = [f"mysql> {' '.join(sql.split())};", line,
           "| " + " | ".join(c.ljust(w[i]) for i, c in enumerate(cols)) + " |", line]
    out += ["| " + " | ".join(v.ljust(w[i]) for i, v in enumerate(r)) + " |" for r in rows]
    out += [line, f"{len(rows)} row(s)", ""]
    print("\n".join(out), flush=True)
    return "\n".join(out)
