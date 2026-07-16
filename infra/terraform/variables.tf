variable "aws_region" {
  description = "AWS region where resources will be created."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefix used for AWS resource names."
  type        = string
  default     = "stock-forecast-api"
}

variable "environment" {
  description = "Environment name."
  type        = string
  default     = "prod"
}

variable "availability_zones" {
  description = "Availability zones for public subnets."
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]

  validation {
    condition     = length(var.availability_zones) > 0
    error_message = "At least one availability zone is required."
  }
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.40.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets."
  type        = list(string)
  default     = ["10.40.1.0/24", "10.40.2.0/24"]

  validation {
    condition     = length(var.public_subnet_cidrs) > 0
    error_message = "At least one public subnet CIDR is required."
  }
}

variable "allowed_http_cidr_blocks" {
  description = "CIDR blocks allowed to access the public ALB."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "ecr_repository_name" {
  description = "ECR repository name for the API image."
  type        = string
  default     = "techchallenge/stock-forecast-api"
}

variable "image_tag" {
  description = "Docker image tag to run in ECS."
  type        = string
  default     = "latest"
}

variable "data_bucket_name" {
  description = "S3 bucket name for datasets. Must be globally unique."
  type        = string
}

variable "models_bucket_name" {
  description = "S3 bucket name for models and reports. Must be globally unique."
  type        = string
}

variable "data_s3_prefix" {
  description = "Optional prefix for objects in the data bucket."
  type        = string
  default     = ""
}

variable "models_s3_prefix" {
  description = "Optional prefix for objects in the models bucket."
  type        = string
  default     = ""
}

variable "container_port" {
  description = "API container port."
  type        = number
  default     = 8000
}

variable "task_cpu" {
  description = "Fargate task CPU units."
  type        = number
  default     = 1024
}

variable "task_memory" {
  description = "Fargate task memory in MiB."
  type        = number
  default     = 3072
}

variable "desired_count" {
  description = "Desired ECS service task count."
  type        = number
  default     = 1
}

variable "github_owner" {
  description = "GitHub organization or user that owns the repository."
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name."
  type        = string
}

variable "github_branch" {
  description = "GitHub branch allowed to assume the deploy role."
  type        = string
  default     = "main"
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub Actions OIDC provider. Set false if it already exists in the AWS account."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Extra tags applied to resources."
  type        = map(string)
  default     = {}
}
