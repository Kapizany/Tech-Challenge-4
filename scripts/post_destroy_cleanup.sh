#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TERRAFORM_DIR="${TERRAFORM_DIR:-$PROJECT_ROOT/infra/terraform}"
TFVARS_PATH="${TFVARS_PATH:-$TERRAFORM_DIR/terraform.tfvars}"

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
PROJECT_NAME="${PROJECT_NAME:-$(tfvar project_name)}"
ENVIRONMENT="${ENVIRONMENT:-$(tfvar environment)}"
ARTIFACT_BUCKET="${ARTIFACT_BUCKET:-$(tfvar artifact_bucket_name)}"
ECR_REPOSITORY="${ECR_REPOSITORY:-$(tfvar ecr_repository_name)}"

if [[ -z "${AWS_REGION:-}" ]]; then
  AWS_REGION="us-east-1"
fi
if [[ -z "${PROJECT_NAME:-}" ]]; then
  PROJECT_NAME="stock-forecast-api"
fi
if [[ -z "${ENVIRONMENT:-}" ]]; then
  ENVIRONMENT="prod"
fi

NAME_PREFIX="${PROJECT_NAME}-${ENVIRONMENT}"
CLUSTER_NAME="${ECS_CLUSTER:-${NAME_PREFIX}-cluster}"
SERVICE_NAME="${ECS_SERVICE:-${NAME_PREFIX}-service}"
RUNTIME_SECRET_NAME="${RUNTIME_SECRET_NAME:-${NAME_PREFIX}/runtime-config}"
GITHUB_ROLE_NAME="${GITHUB_ROLE_NAME:-${NAME_PREFIX}-github-actions-role}"
TASK_ROLE_NAME="${TASK_ROLE_NAME:-${NAME_PREFIX}-ecs-task-role}"
EXECUTION_ROLE_NAME="${EXECUTION_ROLE_NAME:-${NAME_PREFIX}-ecs-execution-role}"
LOG_GROUP_NAME="${LOG_GROUP_NAME:-/ecs/${NAME_PREFIX}}"

status_ok=true

check_absent() {
  local label="$1"
  local command="$2"
  if bash -c "$command" >/dev/null 2>&1; then
    echo "STILL EXISTS: $label"
    status_ok=false
  else
    echo "absent: $label"
  fi
}

echo "Checking AWS resources after terraform destroy..."
echo "Region: $AWS_REGION"

if [[ -n "${ARTIFACT_BUCKET:-}" && "$ARTIFACT_BUCKET" != CHANGE_ME* ]]; then
  check_absent "S3 bucket $ARTIFACT_BUCKET" \
    "aws s3api head-bucket --bucket '$ARTIFACT_BUCKET' --region '$AWS_REGION'"
fi

if [[ -n "${ECR_REPOSITORY:-}" && "$ECR_REPOSITORY" != CHANGE_ME* ]]; then
  check_absent "ECR repository $ECR_REPOSITORY" \
    "aws ecr describe-repositories --repository-names '$ECR_REPOSITORY' --region '$AWS_REGION'"
fi

check_absent "ECS cluster $CLUSTER_NAME" \
  "aws ecs describe-clusters --clusters '$CLUSTER_NAME' --region '$AWS_REGION' --query 'clusters[?status!=\`INACTIVE\`]' --output text | grep -q ."

check_absent "ECS service $SERVICE_NAME" \
  "aws ecs describe-services --cluster '$CLUSTER_NAME' --services '$SERVICE_NAME' --region '$AWS_REGION' --query 'services[?status!=\`INACTIVE\`]' --output text | grep -q ."

check_absent "Secrets Manager secret $RUNTIME_SECRET_NAME" \
  "aws secretsmanager describe-secret --secret-id '$RUNTIME_SECRET_NAME' --region '$AWS_REGION'"

check_absent "CloudWatch log group $LOG_GROUP_NAME" \
  "aws logs describe-log-groups --log-group-name-prefix '$LOG_GROUP_NAME' --region '$AWS_REGION' --query 'logGroups[?logGroupName==\`$LOG_GROUP_NAME\`]' --output text | grep -q ."

check_absent "IAM role $GITHUB_ROLE_NAME" \
  "aws iam get-role --role-name '$GITHUB_ROLE_NAME'"
check_absent "IAM role $TASK_ROLE_NAME" \
  "aws iam get-role --role-name '$TASK_ROLE_NAME'"
check_absent "IAM role $EXECUTION_ROLE_NAME" \
  "aws iam get-role --role-name '$EXECUTION_ROLE_NAME'"

echo "Cleaning local Terraform files..."
rm -rf "$TERRAFORM_DIR/.terraform"
rm -f "$TERRAFORM_DIR/.terraform.lock.hcl"
rm -f "$TERRAFORM_DIR/terraform.tfstate"
rm -f "$TERRAFORM_DIR/terraform.tfstate.backup"
rm -f "$TERRAFORM_DIR"/crash.log
rm -f "$TERRAFORM_DIR"/crash.*.log

echo "Local Terraform cleanup complete."

if [[ "$status_ok" == false ]]; then
  echo "Some AWS resources still exist. Review the lines marked STILL EXISTS above." >&2
  exit 1
fi

echo "Post-destroy check passed."
