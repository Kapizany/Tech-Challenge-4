#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TFVARS_PATH="${TFVARS_PATH:-$PROJECT_ROOT/infra/terraform/terraform.tfvars}"

tfvar() {
  local key="$1"
  if [[ ! -f "$TFVARS_PATH" ]]; then
    return 0
  fi
  awk -F '=' -v key="$key" '
    $1 ~ "^[[:space:]]*" key "[[:space:]]*$" {
      value=$2
      sub(/^[[:space:]]*/, "", value)
      sub(/[[:space:]]*$/, "", value)
      gsub(/^"|"$/, "", value)
      print value
      exit
    }
  ' "$TFVARS_PATH"
}

join_s3_uri() {
  local bucket="$1"
  local prefix="${2:-}"
  local suffix="$3"
  prefix="${prefix#/}"
  prefix="${prefix%/}"
  suffix="${suffix#/}"
  if [[ -n "$prefix" ]]; then
    printf 's3://%s/%s/%s\n' "$bucket" "$prefix" "$suffix"
  else
    printf 's3://%s/%s\n' "$bucket" "$suffix"
  fi
}

AWS_REGION="${AWS_REGION:-$(tfvar aws_region)}"
ARTIFACT_BUCKET="${ARTIFACT_BUCKET:-$(tfvar artifact_bucket_name)}"
DATA_S3_PREFIX="${DATA_S3_PREFIX:-$(tfvar data_s3_prefix)}"
MODELS_S3_PREFIX="${MODELS_S3_PREFIX:-$(tfvar models_s3_prefix)}"

if [[ -z "${AWS_REGION:-}" ]]; then
  AWS_REGION="us-east-1"
fi

if [[ -z "${ARTIFACT_BUCKET:-}" || "$ARTIFACT_BUCKET" == CHANGE_ME* ]]; then
  echo "ARTIFACT_BUCKET is missing. Set ARTIFACT_BUCKET or fill artifact_bucket_name in $TFVARS_PATH." >&2
  exit 1
fi

echo "Using bucket: $ARTIFACT_BUCKET"
echo "Using region: $AWS_REGION"
echo "Data prefix: ${DATA_S3_PREFIX:-<empty>}"
echo "Models prefix: ${MODELS_S3_PREFIX:-<empty>}"

if [[ -d "$PROJECT_ROOT/data" ]]; then
  data_uri="$(join_s3_uri "$ARTIFACT_BUCKET" "$DATA_S3_PREFIX" "data")"
  echo "Syncing data/ -> $data_uri"
  aws s3 sync "$PROJECT_ROOT/data" "$data_uri" --region "$AWS_REGION"
else
  echo "Skipping data/: directory not found."
fi

if [[ -d "$PROJECT_ROOT/models" ]]; then
  models_uri="$(join_s3_uri "$ARTIFACT_BUCKET" "$MODELS_S3_PREFIX" "models")"
  echo "Syncing models/ -> $models_uri"
  aws s3 sync "$PROJECT_ROOT/models" "$models_uri" --region "$AWS_REGION"
else
  echo "Skipping models/: directory not found."
fi

if [[ -d "$PROJECT_ROOT/reports" ]]; then
  reports_uri="$(join_s3_uri "$ARTIFACT_BUCKET" "$MODELS_S3_PREFIX" "reports")"
  echo "Syncing reports/ -> $reports_uri"
  aws s3 sync "$PROJECT_ROOT/reports" "$reports_uri" --region "$AWS_REGION"
else
  echo "Skipping reports/: directory not found."
fi

echo "S3 sync complete."
