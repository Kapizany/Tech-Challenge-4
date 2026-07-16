output "alb_dns_name" {
  description = "Public DNS name for the API ALB."
  value       = aws_lb.api.dns_name
}

output "api_url" {
  description = "HTTP URL for the deployed API."
  value       = "http://${aws_lb.api.dns_name}"
}

output "ecs_cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.api.name
}

output "ecs_service_name" {
  description = "ECS service name."
  value       = aws_ecs_service.api.name
}

output "ecr_repository_url" {
  description = "ECR repository URL used by GitHub Actions and ECS."
  value       = aws_ecr_repository.api.repository_url
}

output "artifact_bucket_name" {
  description = "S3 bucket for data, model and report artifacts."
  value       = aws_s3_bucket.artifacts.bucket
}

output "data_bucket_name" {
  description = "S3 bucket used by DATA_S3_BUCKET."
  value       = aws_s3_bucket.artifacts.bucket
}

output "models_bucket_name" {
  description = "S3 bucket used by MODELS_S3_BUCKET."
  value       = aws_s3_bucket.artifacts.bucket
}

output "github_actions_role_arn" {
  description = "Role ARN to store as GitHub secret AWS_ROLE_TO_ASSUME."
  value       = aws_iam_role.github_actions.arn
}

output "github_actions_oidc_subject" {
  description = "GitHub OIDC subject patterns allowed to assume the GitHub Actions role."
  value       = local.github_oidc_subject_patterns
}

output "runtime_config_secret_arn" {
  description = "Secrets Manager secret ARN used by the ECS task."
  value       = aws_secretsmanager_secret.runtime_config.arn
}

output "cloudwatch_log_group_name" {
  description = "CloudWatch log group used by the API container."
  value       = aws_cloudwatch_log_group.api.name
}

output "task_execution_role_arn" {
  description = "ECS task execution role ARN."
  value       = aws_iam_role.ecs_execution.arn
}

output "task_role_arn" {
  description = "ECS task role ARN with S3 read permissions."
  value       = aws_iam_role.ecs_task.arn
}
