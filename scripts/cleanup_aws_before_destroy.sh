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

AWS_REGION="${AWS_REGION:-$(tfvar aws_region)}"
ARTIFACT_BUCKET="${ARTIFACT_BUCKET:-$(tfvar artifact_bucket_name)}"
ECR_REPOSITORY="${ECR_REPOSITORY:-$(tfvar ecr_repository_name)}"

if [[ -z "${AWS_REGION:-}" ]]; then
  AWS_REGION="us-east-1"
fi

empty_versioned_bucket() {
  local bucket="$1"
  local versions_file
  local markers_file
  versions_file="$(mktemp /tmp/s3-versions.XXXXXX.json)"
  markers_file="$(mktemp /tmp/s3-markers.XXXXXX.json)"

  if ! aws s3api head-bucket --bucket "$bucket" --region "$AWS_REGION" >/dev/null 2>&1; then
    echo "S3 bucket not found or not accessible, skipping: $bucket"
    rm -f "$versions_file" "$markers_file"
    return 0
  fi

  echo "Emptying versioned bucket: $bucket"
  while true; do
    aws s3api list-object-versions \
      --bucket "$bucket" \
      --region "$AWS_REGION" \
      --max-items 1000 \
      --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' \
      --output json > "$versions_file"

    local version_count
    version_count="$(aws s3api list-object-versions \
      --bucket "$bucket" \
      --region "$AWS_REGION" \
      --max-items 1000 \
      --query 'length(Versions || `[]`)' \
      --output text)"

    if [[ "$version_count" == "0" ]]; then
      break
    fi

    aws s3api delete-objects \
      --bucket "$bucket" \
      --delete "file://$versions_file" \
      --region "$AWS_REGION" >/dev/null
  done

  while true; do
    aws s3api list-object-versions \
      --bucket "$bucket" \
      --region "$AWS_REGION" \
      --max-items 1000 \
      --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' \
      --output json > "$markers_file"

    local marker_count
    marker_count="$(aws s3api list-object-versions \
      --bucket "$bucket" \
      --region "$AWS_REGION" \
      --max-items 1000 \
      --query 'length(DeleteMarkers || `[]`)' \
      --output text)"

    if [[ "$marker_count" == "0" ]]; then
      break
    fi

    aws s3api delete-objects \
      --bucket "$bucket" \
      --delete "file://$markers_file" \
      --region "$AWS_REGION" >/dev/null
  done

  rm -f "$versions_file" "$markers_file"
}

delete_ecr_repository_images() {
  local repository="$1"
  echo "Deleting ECR images from: $repository"

  if ! aws ecr describe-repositories \
    --repository-names "$repository" \
    --region "$AWS_REGION" >/dev/null 2>&1; then
    echo "ECR repository not found, skipping: $repository"
    return 0
  fi

  while true; do
    local image_ids
    image_ids="$(aws ecr list-images \
      --repository-name "$repository" \
      --region "$AWS_REGION" \
      --max-items 100 \
      --query 'imageIds' \
      --output json)"

    if [[ "$image_ids" == "[]" || -z "$image_ids" ]]; then
      break
    fi

    aws ecr batch-delete-image \
      --repository-name "$repository" \
      --region "$AWS_REGION" \
      --image-ids "$image_ids" >/dev/null
  done
}

if [[ -n "${ARTIFACT_BUCKET:-}" && "$ARTIFACT_BUCKET" != CHANGE_ME* ]]; then
  empty_versioned_bucket "$ARTIFACT_BUCKET"
else
  echo "ARTIFACT_BUCKET is missing, skipping S3 cleanup."
fi

if [[ -n "${ECR_REPOSITORY:-}" && "$ECR_REPOSITORY" != CHANGE_ME* ]]; then
  delete_ecr_repository_images "$ECR_REPOSITORY"
else
  echo "ECR_REPOSITORY is missing, skipping ECR cleanup."
fi

echo "AWS cleanup complete. You can run: cd infra/terraform && terraform destroy"
