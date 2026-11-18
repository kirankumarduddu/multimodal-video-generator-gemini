#!/usr/bin/env bash
# Prepare a Google Cloud project for Multimodal Video Generator (macOS / Linux).
#   ./scripts/setup-gcp.sh my-project me@example.com [bucket]
#   SKIP_GRANT=1 ./scripts/setup-gcp.sh my-project me@example.com   # not an owner: ask your admin
set -euo pipefail
PROJECT="${1:?usage: setup-gcp.sh PROJECT_ID EMAIL [BUCKET]}"
EMAIL="${2:?usage: setup-gcp.sh PROJECT_ID EMAIL [BUCKET]}"
BUCKET="${3:-}"
step() { printf '\n== %s\n' "$1"; }

command -v gcloud >/dev/null || { echo "gcloud CLI not found: https://cloud.google.com/sdk/docs/install"; exit 1; }

step "Sign in to the gcloud CLI (opens a browser)"
gcloud auth login --update-adc
gcloud config set project "$PROJECT"

step "Enable the Vertex AI API"
gcloud services enable aiplatform.googleapis.com --project "$PROJECT"
if [ -n "$BUCKET" ]; then gcloud services enable storage.googleapis.com --project "$PROJECT"; fi

if [ -z "${SKIP_GRANT:-}" ]; then
  step "Grant $EMAIL the roles it needs (needs owner or IAM admin)"
  gcloud projects add-iam-policy-binding "$PROJECT" --member="user:$EMAIL" --role="roles/aiplatform.user" --condition=None >/dev/null
  gcloud projects add-iam-policy-binding "$PROJECT" --member="user:$EMAIL" --role="roles/serviceusage.serviceUsageConsumer" --condition=None >/dev/null
  if [ -n "$BUCKET" ]; then gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="user:$EMAIL" --role="roles/storage.objectAdmin" >/dev/null; fi
else
  echo "Skipped. Ask an owner to run:"
  echo "  gcloud projects add-iam-policy-binding $PROJECT --member=user:$EMAIL --role=roles/aiplatform.user"
  echo "  gcloud projects add-iam-policy-binding $PROJECT --member=user:$EMAIL --role=roles/serviceusage.serviceUsageConsumer"
fi

step "Application Default Credentials for the mvg CLI (opens a browser)"
gcloud auth application-default login
gcloud auth application-default set-quota-project "$PROJECT"

step "Done. Now run: mvg doctor"
