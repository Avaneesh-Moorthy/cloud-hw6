#!/bin/bash
# =============================================================================
# run_hw6.sh - ONE command for HW6:
#   1. enables (starts) the Cloud SQL database and pauses the hourly auto-stop monitor
#   2. creates a VM whose startup script converts the data to 3NF and runs both models
#   3. waits for the VM to finish (marker file in the bucket)
#   4. prints the output files from the bucket on the terminal
#   5. deletes the VM, stops the database, re-enables the monitor (also on error / Ctrl+C)
#
#   cd hw6 && bash run_hw6.sh            # optional: SEED=7 bash run_hw6.sh
# Requires the HW5 database (hw5-db, database hw5, secret hw5-db-password) to exist.
# =============================================================================
set -uo pipefail
PROJECT_ID="cedar-pottery-508921-u1"
REGION="us-central1"; ZONE="us-central1-a"
BUCKET="cedar-pottery-508921-u1-pages"; PREFIX="hw6_output/"
SQL_INSTANCE="hw5-db"; DB_SECRET="hw5-db-password"
VM="hw6-ml"; VM_TYPE="e2-medium"
SA="hw6-ml@${PROJECT_ID}.iam.gserviceaccount.com"
REPO="https://github.com/Avaneesh-Moorthy/cloud-hw6.git"
JOB="hw5-db-check-hourly"
SEED=${SEED:-42}
HERE="$(cd "$(dirname "$0")" && pwd)"
G="gcloud --project=$PROJECT_ID --quiet"
say() { echo; echo "==> $*"; }

finish() {
  say "Cleaning up: deleting VM, stopping the database"
  $G compute instances describe "$VM" --zone="$ZONE" >/dev/null 2>&1 && \
    $G compute instances delete "$VM" --zone="$ZONE"
  $G sql instances patch "$SQL_INSTANCE" --activation-policy=NEVER >/dev/null 2>&1 && \
    echo "Cloud SQL $SQL_INSTANCE stopped"
  $G scheduler jobs resume "$JOB" --location="$REGION" >/dev/null 2>&1 && \
    echo "hourly DB monitor re-enabled"
  $G sql instances list --format="table(name,state,settings.activationPolicy)"
  $G compute instances list
}
trap finish EXIT

say "Service account for the model VM (least privilege)"
$G iam service-accounts describe "$SA" >/dev/null 2>&1 || {
  $G iam service-accounts create hw6-ml --display-name="HW6 model VM"; sleep 10; }
$G projects add-iam-policy-binding "$PROJECT_ID" --condition=None \
  --member="serviceAccount:$SA" --role=roles/cloudsql.client >/dev/null
$G secrets add-iam-policy-binding "$DB_SECRET" \
  --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --project="$PROJECT_ID" \
  --member="serviceAccount:$SA" --role=roles/storage.objectUser --quiet >/dev/null

say "Enabling (starting) the database"
$G scheduler jobs pause "$JOB" --location="$REGION" >/dev/null 2>&1 || true
$G sql instances patch "$SQL_INSTANCE" --activation-policy=ALWAYS

say "Removing old results from gs://$BUCKET/$PREFIX"
gcloud storage rm "gs://$BUCKET/${PREFIX}**" --quiet >/dev/null 2>&1 || true

say "Creating VM $VM ($VM_TYPE) - its startup script does all the work"
$G compute instances create "$VM" --zone="$ZONE" --machine-type="$VM_TYPE" \
  --image-family=debian-12 --image-project=debian-cloud \
  --service-account="$SA" --scopes=cloud-platform \
  --metadata="repo=$REPO,bucket=$BUCKET,prefix=$PREFIX,seed=$SEED,project=$PROJECT_ID,sql-instance=$PROJECT_ID:$REGION:$SQL_INSTANCE" \
  --metadata-from-file=startup-script="$HERE/startup_ml.sh" || exit 1

say "Waiting for the VM to finish (usually 4-8 minutes)"
for i in $(seq 1 90); do
  if gcloud storage ls "gs://$BUCKET/${PREFIX}_DONE" >/dev/null 2>&1; then RESULT=done; break; fi
  if gcloud storage ls "gs://$BUCKET/${PREFIX}_FAILED" >/dev/null 2>&1; then RESULT=failed; break; fi
  printf '.'; sleep 20
done
echo

if [ "${RESULT:-timeout}" != "done" ]; then
  say "Run did not succeed ($RESULT) - VM log:"
  gcloud storage cat "gs://$BUCKET/${PREFIX}run_log.txt" 2>/dev/null | tail -60
  exit 1
fi

say "Files in gs://$BUCKET/$PREFIX"
gcloud storage ls -l "gs://$BUCKET/$PREFIX"
say "gs://$BUCKET/${PREFIX}run_log.txt (3NF migration checks + model log)"
gcloud storage cat "gs://$BUCKET/${PREFIX}run_log.txt"
say "gs://$BUCKET/${PREFIX}model_summary.txt"
gcloud storage cat "gs://$BUCKET/${PREFIX}model_summary.txt"
for f in ip_country_test_predictions.csv income_test_predictions.csv; do
  say "gs://$BUCKET/${PREFIX}$f (first 15 lines; full file in the bucket)"
  gcloud storage cat "gs://$BUCKET/${PREFIX}$f" | head -15
  echo "... $(gcloud storage cat "gs://$BUCKET/${PREFIX}$f" | wc -l) lines in total"
done
