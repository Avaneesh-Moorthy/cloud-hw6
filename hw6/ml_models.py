"""
ml_models.py - HW6: two models trained on the data the HW5 web server stored
(read from the 3NF tables created by normalize.py).

Model 1  client IP  -> country
    Data: the `client_ip` table (one row per distinct IP, joined to `country`).
    Split by IP, so no test IP was ever seen in training.
    Feature: the IPv4 address as one 32-bit integer (a.b.c.d -> a*2^24 + b*2^16 + c*2^8 + d).
    Model: DecisionTreeClassifier. The client hands out IPs from per-country address
    blocks (CIDR ranges), so each country owns contiguous intervals of the integer line;
    a decision tree learns exactly such interval boundaries (each split is "ip <= t").

Model 2  other fields -> income group
    Data: every request that carries the client headers (`request` joined to `client_ip`
    and `country`). Candidate feature sets are compared with 5-fold cross-validation on
    the training set only; the best one is refit on all training data and scored once on
    the held-out test set. The same is repeated for several split seeds to show how much
    the result moves with the seed.

Outputs (also uploaded to gs://<bucket>/<prefix>):
    ip_country_test_predictions.csv  client_ip, actual_country, predicted_country, correct
    income_test_predictions.csv      fields used, actual_income, predicted_income, correct
    model_summary.txt                accuracies, model details, seed study

usage: python3 ml_models.py --instance P:R:I [--bucket B] [--prefix hw6_output/] [--seed 42]
"""
import argparse
import datetime
import io
import os
import sys
import time

import numpy as np
import pandas as pd
import sqlalchemy
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.naive_bayes import CategoricalNB
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OrdinalEncoder
from sklearn.tree import DecisionTreeClassifier

import db

IP_SQL = """
    SELECT ci.client_ip, c.country_name AS country
    FROM client_ip AS ci JOIN country AS c ON c.country_id = ci.country_id
"""
REQ_SQL = """
    SELECT n.client_ip, c.country_name AS country, n.gender, n.age_group, n.income_group,
           HOUR(n.client_time) AS hour, n.requested_file
    FROM request AS n
    JOIN client_ip AS ci ON ci.client_ip = n.client_ip
    JOIN country  AS c  ON c.country_id = ci.country_id
    WHERE n.income_group IS NOT NULL AND n.age_group IS NOT NULL
      AND n.gender IS NOT NULL AND n.client_time IS NOT NULL
"""
AGE_ORDER = ["0-16", "17-25", "26-35", "36-45", "46-55", "56-65", "66-75", "76+"]


def log(*a):
    print(*a, flush=True)


def ip_to_int(s):
    o = s.str.split(".", expand=True).astype(np.int64).to_numpy()
    return o[:, 0] * 16777216 + o[:, 1] * 65536 + o[:, 2] * 256 + o[:, 3]


# ------------------------------------------------------------------- model 1
def model_ip_country(ips, seed):
    ips = ips[ips.client_ip.str.fullmatch(r"\d+\.\d+\.\d+\.\d+")].copy()
    ips["ip_int"] = ip_to_int(ips.client_ip)
    # countries with a single IP cannot be stratified; put them in training
    counts = ips.country.value_counts()
    strat = ips.country.where(ips.country.map(counts) >= 2, "__rare__")
    tr, te = train_test_split(ips, test_size=0.2, random_state=seed, stratify=strat)
    model = DecisionTreeClassifier(random_state=seed)
    t = time.perf_counter()
    model.fit(tr[["ip_int"]], tr.country)
    fit_s = time.perf_counter() - t
    pred = model.predict(te[["ip_int"]])
    out = te[["client_ip", "country"]].rename(columns={"country": "actual_country"})
    out["predicted_country"] = pred
    out["correct"] = out.actual_country == out.predicted_country
    acc = out.correct.mean()
    info = {"train_rows": len(tr), "test_rows": len(te), "classes": ips.country.nunique(),
            "accuracy": acc, "fit_seconds": fit_s,
            "tree_leaves": model.get_n_leaves(), "tree_depth": model.get_depth()}
    return out.sort_values("client_ip"), info


# ------------------------------------------------------------------- model 2
def income_candidates(seed):
    cat = lambda: OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)  # noqa: E731
    return {
        "age only (Naive Bayes)":
            (["age_group"], make_pipeline(cat(), CategoricalNB(min_categories=None))),
        "age + gender (Naive Bayes)":
            (["age_group", "gender"], make_pipeline(cat(), CategoricalNB())),
        "age + gender (decision tree)":
            (["age_group", "gender"], make_pipeline(cat(), DecisionTreeClassifier(random_state=seed))),
        "age + gender + hour + country (decision tree, depth 8)":
            (["age_group", "gender", "hour", "country"],
             make_pipeline(cat(), DecisionTreeClassifier(max_depth=8, min_samples_leaf=20,
                                                         random_state=seed))),
    }


def model_income(reqs, seed):
    reqs = reqs.copy()
    reqs["hour"] = reqs["hour"].astype(int).astype(str)
    tr, te = train_test_split(reqs, test_size=0.2, random_state=seed, stratify=reqs.income_group)
    majority = tr.income_group.value_counts().idxmax()
    cv = {}
    for name, (feats, pipe) in income_candidates(seed).items():
        cv[name] = cross_val_score(pipe, tr[feats], tr.income_group, cv=5,
                                   scoring="accuracy").mean()
    best = max(cv, key=cv.get)
    feats, pipe = income_candidates(seed)[best]
    pipe.fit(tr[feats], tr.income_group)
    pred = pipe.predict(te[feats])
    out = te[feats].copy()
    out.insert(0, "client_ip", te.client_ip)
    out["actual_income"] = te.income_group
    out["predicted_income"] = pred
    out["correct"] = out.actual_income == out.predicted_income
    # what the model learned: predicted income for every age (and gender) value
    grid = pd.DataFrame([{"age_group": a, "gender": g, "hour": "12", "country": te.country.iloc[0]}
                         for a in AGE_ORDER for g in ("Female", "Male")])
    grid["predicted_income"] = pipe.predict(grid[feats])
    # how income depends on age in the training data
    ct = pd.crosstab(tr.age_group, tr.income_group, normalize="index").reindex(AGE_ORDER).round(3)
    info = {"train_rows": len(tr), "test_rows": len(te), "classes": reqs.income_group.nunique(),
            "baseline_majority": (te.income_group == majority).mean(),
            "cv": cv, "best": best, "features": feats, "accuracy": out.correct.mean(),
            "grid": grid[[c for c in ("age_group", "gender") if c in grid] + ["predicted_income"]],
            "age_income_table": ct}
    return out, info


def seed_study(reqs, seeds):
    """Test accuracy of the chosen-type model (age + gender NB) for different split seeds."""
    reqs = reqs.copy()
    reqs["hour"] = reqs["hour"].astype(int).astype(str)
    res = []
    for s in seeds:
        tr, te = train_test_split(reqs, test_size=0.2, random_state=s, stratify=reqs.income_group)
        feats, pipe = income_candidates(s)["age + gender (Naive Bayes)"]
        pipe.fit(tr[feats], tr.income_group)
        res.append((s, (pipe.predict(te[feats]) == te.income_group).mean()))
    return res


# --------------------------------------------------------------------- output
def upload(bucket_name, prefix, files):
    from google.cloud import storage
    bucket = storage.Client().bucket(bucket_name)
    for f in files:
        blob = bucket.blob(prefix + os.path.basename(f))
        blob.upload_from_filename(f, content_type="text/csv" if f.endswith(".csv") else "text/plain")
        log(f"uploaded gs://{bucket_name}/{blob.name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="cedar-pottery-508921-u1")
    ap.add_argument("--instance", default="cedar-pottery-508921-u1:us-central1:hw5-db")
    ap.add_argument("--db-name", default="hw5")
    ap.add_argument("--db-user", default="hw5app")
    ap.add_argument("--db-secret", default="hw5-db-password")
    ap.add_argument("--bucket", default="cedar-pottery-508921-u1-pages")
    ap.add_argument("--prefix", default="hw6_output/")
    ap.add_argument("--seed", type=int, default=42, help="train/test split + model seed")
    ap.add_argument("--outdir", default="/var/tmp/hw6_output")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--db-url", help="testing only: SQLAlchemy URL instead of Cloud SQL")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    engine = (sqlalchemy.create_engine(a.db_url) if a.db_url else
              db.make_engine(a.instance, a.db_user, db.get_password(a.project, a.db_secret),
                             a.db_name, pool_size=1))
    t0 = time.perf_counter()
    with engine.connect() as c:
        ips = pd.read_sql(sqlalchemy.text(IP_SQL), c)
        reqs = pd.read_sql(sqlalchemy.text(REQ_SQL), c)
    log(f"loaded {len(ips)} distinct IPs and {len(reqs)} requests in {time.perf_counter()-t0:.1f}s")

    out1, i1 = model_ip_country(ips, a.seed)
    log(f"model 1 (IP -> country): test accuracy {i1['accuracy']:.4%}")
    out2, i2 = model_income(reqs, a.seed)
    log(f"model 2 (-> income): {i2['best']}: test accuracy {i2['accuracy']:.4%}")
    seeds = seed_study(reqs, [1, 7, 42, 123, 2026, 31337])

    f1 = os.path.join(a.outdir, "ip_country_test_predictions.csv")
    f2 = os.path.join(a.outdir, "income_test_predictions.csv")
    fs = os.path.join(a.outdir, "model_summary.txt")
    out1.to_csv(f1, index=False)
    out2.to_csv(f2, index=False)

    s = io.StringIO()
    p = lambda *x: print(*x, file=s)  # noqa: E731
    p("HW6 model results", datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    p(f"split/model seed: {a.seed}   (80% train / 20% test)")
    p()
    p("MODEL 1: client IP -> country")
    p(f"  data: {i1['train_rows'] + i1['test_rows']} distinct IPv4 addresses, {i1['classes']} countries")
    p(f"  model: DecisionTreeClassifier on the IP as a 32-bit integer "
      f"({i1['tree_leaves']} leaves, depth {i1['tree_depth']}, fit in {i1['fit_seconds']:.2f}s)")
    p(f"  train {i1['train_rows']} / test {i1['test_rows']} IPs (no IP in both)")
    p(f"  TEST ACCURACY: {i1['accuracy']:.4%}  ({int(out1.correct.sum())}/{len(out1)})")
    if (~out1.correct).any():
        p("  misclassified:")
        p(out1[~out1.correct].head(20).to_string(index=False))
    p()
    p("MODEL 2: income group")
    p(f"  data: {i2['train_rows'] + i2['test_rows']} requests with all headers, {i2['classes']} income groups")
    p(f"  baseline (always predict the most common income): {i2['baseline_majority']:.2%}")
    p("  5-fold cross-validation accuracy on the TRAINING set:")
    for k, v in i2["cv"].items():
        p(f"    {v:.2%}  {k}")
    p(f"  chosen: {i2['best']}  (features: {', '.join(i2['features'])})")
    p(f"  TEST ACCURACY: {i2['accuracy']:.4%}  ({int(out2.correct.sum())}/{len(out2)})")
    p("  income distribution per age group in the training data (row = age, share of each income):")
    p(i2["age_income_table"].to_string())
    p("  what the chosen model predicts:")
    p(i2["grid"].drop_duplicates().to_string(index=False))
    p("  same model type, different split seeds -> test accuracy:")
    for sd, acc in seeds:
        p(f"    seed {sd:>6}: {acc:.2%}")
    accs = [x for _, x in seeds]
    p(f"    mean {np.mean(accs):.2%}, min {min(accs):.2%}, max {max(accs):.2%}")
    summary = s.getvalue()
    open(fs, "w").write(summary)
    log(summary)

    if not a.no_upload:
        upload(a.bucket, a.prefix, [f1, f2, fs])


if __name__ == "__main__":
    sys.exit(main())
