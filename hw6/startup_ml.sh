#!/bin/bash
# startup_ml.sh - startup script for the HW6 model VM (passed with --metadata-from-file).
# Runs once (lock file): installs Python, clones the repo, converts the database to 3NF
# (normalize.py), trains and tests both models (ml_models.py), uploads the result files
# and the run log to the bucket, then writes a _DONE (or _FAILED) marker there.
if [ -f /var/log/startup_already_done ]; then
  echo "Startup script already ran once. Skipping."
  exit 0
fi
touch /var/log/startup_already_done

md() { curl -sf -H "Metadata-Flavor: Google" \
       "http://metadata.google.internal/computeMetadata/v1/instance/attributes/$1"; }
REPO=$(md repo); BUCKET=$(md bucket); PREFIX=$(md prefix); SEED=$(md seed)
SQL_INSTANCE=$(md sql-instance); PROJECT=$(md project)
LOG=/var/log/hw6_run.log

(
  set -e
  echo "== $(date -u) installing"
  apt-get update -y
  apt-get install -y python3-venv git
  rm -rf /opt/hw6 && git clone --depth 1 "$REPO" /opt/hw6
  python3 -m venv /opt/hw6/venv
  /opt/hw6/venv/bin/pip install -q -r /opt/hw6/hw6/requirements.txt
  cd /opt/hw6/hw6
  echo "== $(date -u) normalize.py (3NF schema + data transfer)"
  /opt/hw6/venv/bin/python -u normalize.py --project "$PROJECT" --instance "$SQL_INSTANCE"
  echo "== $(date -u) ml_models.py"
  /opt/hw6/venv/bin/python -u ml_models.py --project "$PROJECT" --instance "$SQL_INSTANCE" \
      --bucket "$BUCKET" --prefix "$PREFIX" --seed "$SEED"
  echo "== $(date -u) finished"
) > "$LOG" 2>&1
STATUS=$?

gcloud storage cp "$LOG" "gs://$BUCKET/${PREFIX}run_log.txt"
if [ $STATUS -eq 0 ]; then MARK=_DONE; else MARK=_FAILED; fi
echo "exit=$STATUS" | gcloud storage cp - "gs://$BUCKET/${PREFIX}$MARK"
