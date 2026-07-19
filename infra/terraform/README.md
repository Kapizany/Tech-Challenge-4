# Terraform AWS Infrastructure

This Terraform stack provisions the AWS infrastructure needed to run the stock forecast API on ECS Fargate.

The default task size is `512` CPU units and `2048` MiB memory, which keeps Fargate cost low while giving TensorFlow/Keras more room to load the saved models. To reduce cost further, you can test `task_cpu = 256` and `task_memory = 1024`, but that may cause out-of-memory restarts depending on model size.

## Resources

- Single S3 bucket for data, model and report artifacts.
- ECR repository for the API image.
- ECS cluster, task definition and service.
- Application Load Balancer with `/health` target health check.
- VPC, public subnets, route table, Internet Gateway and security groups.
- CloudWatch log group.
- IAM roles for ECS execution, ECS task S3 reads and GitHub Actions ECR publishing.
- Secrets Manager secret containing runtime S3 configuration.
- Optional GitHub Actions OIDC provider.

## Usage

Copy the example variables file:

```bash
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars
```

Edit:

- `github_owner`
- `github_repo`
- `artifact_bucket_name`
- `data_s3_prefix`
- `models_s3_prefix`

Then run:

```bash
cd infra/terraform
terraform init
terraform plan
terraform apply
```

After apply, copy `github_actions_role_arn` from the Terraform outputs and create this GitHub secret:

```text
AWS_ROLE_TO_ASSUME=<github_actions_role_arn>
```

## Existing Resources

Terraform does not automatically adopt pre-existing resources with the same names. If a bucket, ECR repository, OIDC provider or IAM role already exists outside this state, either:

- import it with `terraform import`;
- change the variable value to create a new resource;
- set `create_github_oidc_provider = false` if only the GitHub OIDC provider already exists.

S3 bucket names are globally unique, so `artifact_bucket_name` must be unique across AWS. Data and model files are separated by prefix inside the same bucket.
