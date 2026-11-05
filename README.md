# CS528 HW6: 3NF schema + two models on the HW5 data

Everything is in [`hw6/`](hw6/). It builds on the HW5 Cloud SQL database (`hw5-db`, database `hw5`).

```bash
git clone https://github.com/Avaneesh-Moorthy/cloud-hw6.git && cd cloud-hw6/hw6
bash run_hw6.sh        # start DB -> VM runs normalize.py + ml_models.py -> print results -> delete VM, stop DB
```

| File | Purpose |
|---|---|
| `run_hw6.sh` | the one command: enable DB, create VM, wait, print outputs from the bucket, delete VM, stop DB |
| `startup_ml.sh` | VM startup script (run-once): install, run `normalize.py` then `ml_models.py` |
| `schema_3nf.sql` | new 3NF schema: `country`, `client_ip`, `request`, view `failed_request` |
| `migrate_3nf.sql` | queries that move the HW5 data into the 3NF tables |
| `check_3nf.sql` | checks that the migration is complete and lossless |
| `normalize.py` | runs the three SQL files |
| `ml_models.py` | model 1: IP -> country (decision tree on the 32-bit IP); model 2: -> income |
| `db.py`, `sqlrun.py` | Cloud SQL connection (Cloud SQL Python Connector + Secret Manager), SQL helpers |

Model outputs: `gs://cedar-pottery-508921-u1-pages/hw6_output/`
(`ip_country_test_predictions.csv`, `income_test_predictions.csv`, `model_summary.txt`, `run_log.txt`).
