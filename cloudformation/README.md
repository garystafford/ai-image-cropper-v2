# CloudFormation Deployment

This directory contains CloudFormation templates and deployment scripts for the AI Image Cropper v2 infrastructure on AWS.

## Prerequisites

- AWS CLI installed and configured
- AWS credentials with CloudFormation, ECR, EFS, and IAM permissions
- Bash shell

## Files

### CloudFormation Templates (deployed in order)

- `01-ecr-repositories.yaml` - ECR repositories for frontend and backend images
- `02-efs-storage.yaml` - EFS file system for shared storage
- `03-load-balancer.yaml` - ALB, security group, WAF WebACL, and Cognito auth listener
- `04-iam-roles.yaml` - IAM execution and task roles for ECS
- `05-ecs-cluster.yaml` - ECS Fargate cluster and CloudWatch log group
- `06-ecs-service.yaml` - ECS service and task definition
- `07-ecs-application.yaml` - Alternate combined application template
- `08-cognito.yaml` - Cognito User Pool for authentication (optional)
- `09-cloudfront.yaml` - CloudFront distribution and Route 53 DNS (optional)

### Configuration and Scripts

- `common-parameters.json.example` - Example parameters file (copy to `common-parameters.json`)
- `PARAMETERS.md` - Detailed parameter documentation

## Quick Start

### 1. Create Parameters File

```bash
cd cloudformation
cp common-parameters.json.example common-parameters.json
```

Edit `common-parameters.json` with your AWS resource IDs. See [PARAMETERS.md](PARAMETERS.md) for details on each parameter.

### 2. Deploy All Stacks

```bash
cd ..
./deploy-cloudformation.sh
```

The script deploys up to 9 CloudFormation stacks in order, automatically detecting whether to create or update each stack. For existing stacks, the script always attempts an update and gracefully handles "No updates to be performed" responses. Steps 7-9 (Cognito, ALB update, CloudFront) deploy automatically when `AppDomainName`, `CognitoDomainPrefix`, `HostedZoneId`, and `CloudFrontCertificateArn` are configured in `common-parameters.json`.

To reuse an existing Cognito User Pool instead of creating a new one, set `CognitoUserPoolArn`, `CognitoUserPoolClientId`, and `CognitoUserPoolDomain` in `common-parameters.json`. This skips step 7 (Cognito stack creation) and passes the existing pool values directly to the ALB configuration in step 8.

## Configuration

Edit the variables at the top of `deploy-cloudformation.sh`:

```bash
PROJECT_NAME="ai-image-cropper-v2"
ENVIRONMENT="prod"              # Options: dev, staging, prod
REGION="us-east-1"
```

## Stack Names

The script creates stacks with the naming convention `${PROJECT_NAME}-${COMPONENT}-${ENVIRONMENT}`:

- `ai-image-cropper-v2-ecr-prod`
- `ai-image-cropper-v2-efs-prod`
- `ai-image-cropper-v2-alb-prod`
- `ai-image-cropper-v2-iam-prod`
- `ai-image-cropper-v2-cluster-prod`
- `ai-image-cropper-v2-service-prod`
- `ai-image-cropper-v2-cognito-prod` (optional)
- `ai-image-cropper-v2-cloudfront-prod` (optional)

## Manual Deployment (Alternative)

If you prefer to deploy manually:

### Deploy ECR Stack

```bash
aws cloudformation create-stack \
  --stack-name ai-image-cropper-v2-ecr-prod \
  --template-body file://01-ecr-repositories.yaml \
  --parameters \
    ParameterKey=ProjectName,ParameterValue=ai-image-cropper-v2 \
    ParameterKey=Environment,ParameterValue=prod \
  --region us-east-1
```

### Deploy EFS Stack

```bash
aws cloudformation create-stack \
  --stack-name ai-image-cropper-v2-efs-prod \
  --template-body file://02-efs-storage.yaml \
  --parameters \
    ParameterKey=ProjectName,ParameterValue=ai-image-cropper-v2 \
    ParameterKey=Environment,ParameterValue=prod \
    ParameterKey=VpcId,ParameterValue=vpc-xxxxxxxx \
    ParameterKey=SubnetIds,ParameterValue=subnet-xxx\\,subnet-yyy\\,subnet-zzz \
    ParameterKey=ECSSecurityGroupId,ParameterValue=sg-xxxxxxxxxxxxxxxxx \
  --region us-east-1
```

## Update Existing Stacks

The deployment script automatically detects existing stacks and updates them instead of creating new ones. You can also update manually:

```bash
aws cloudformation update-stack \
  --stack-name ai-image-cropper-v2-ecr-prod \
  --template-body file://01-ecr-repositories.yaml \
  --parameters \
    ParameterKey=ProjectName,ParameterValue=ai-image-cropper-v2 \
    ParameterKey=Environment,ParameterValue=prod \
  --region us-east-1
```

## Delete Stacks

To remove all infrastructure, delete in reverse order:

```bash
# Optional stacks (if deployed)
aws cloudformation delete-stack --stack-name ai-image-cropper-v2-cloudfront-prod --region us-east-1
aws cloudformation wait stack-delete-complete --stack-name ai-image-cropper-v2-cloudfront-prod --region us-east-1

aws cloudformation delete-stack --stack-name ai-image-cropper-v2-cognito-prod --region us-east-1
aws cloudformation wait stack-delete-complete --stack-name ai-image-cropper-v2-cognito-prod --region us-east-1

# Core stacks
aws cloudformation delete-stack --stack-name ai-image-cropper-v2-service-prod --region us-east-1
aws cloudformation wait stack-delete-complete --stack-name ai-image-cropper-v2-service-prod --region us-east-1

aws cloudformation delete-stack --stack-name ai-image-cropper-v2-cluster-prod --region us-east-1
aws cloudformation wait stack-delete-complete --stack-name ai-image-cropper-v2-cluster-prod --region us-east-1

aws cloudformation delete-stack --stack-name ai-image-cropper-v2-iam-prod --region us-east-1
aws cloudformation wait stack-delete-complete --stack-name ai-image-cropper-v2-iam-prod --region us-east-1

aws cloudformation delete-stack --stack-name ai-image-cropper-v2-alb-prod --region us-east-1
aws cloudformation wait stack-delete-complete --stack-name ai-image-cropper-v2-alb-prod --region us-east-1

aws cloudformation delete-stack --stack-name ai-image-cropper-v2-efs-prod --region us-east-1
aws cloudformation wait stack-delete-complete --stack-name ai-image-cropper-v2-efs-prod --region us-east-1

aws cloudformation delete-stack --stack-name ai-image-cropper-v2-ecr-prod --region us-east-1
aws cloudformation wait stack-delete-complete --stack-name ai-image-cropper-v2-ecr-prod --region us-east-1
```

**Warning**: The following resources have `DeletionPolicy: Retain` and will **not** be deleted when their stacks are deleted. You must remove them manually if needed:

- ECR repositories (frontend and backend) — including all stored container images
- EFS file system — including all stored ML models
- CloudWatch log group — including all historical logs
- Cognito User Pool — including all user accounts

To force-delete retained resources after stack deletion:

```bash
# Delete ECR repositories
aws ecr delete-repository --repository-name ai-image-cropper-v2-frontend --force --region us-east-1
aws ecr delete-repository --repository-name ai-image-cropper-v2-backend --force --region us-east-1

# Delete EFS file system (get ID from AWS console or CLI)
aws efs delete-file-system --file-system-id fs-xxxxxxxx --region us-east-1
```

## Troubleshooting

### Stack creation fails

Check the CloudFormation events:

```bash
aws cloudformation describe-stack-events \
  --stack-name ai-image-cropper-v2-ecr-prod \
  --region us-east-1 \
  --max-items 10
```

### View stack status

```bash
aws cloudformation describe-stacks \
  --stack-name ai-image-cropper-v2-ecr-prod \
  --region us-east-1
```

### List all stacks

```bash
aws cloudformation list-stacks \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
  --region us-east-1
```

## Build and Deploy Images

After deploying the CloudFormation stacks, build and push Docker images to ECR:

```bash
./update_ecs_task.sh
```

This script builds both frontend and backend images, pushes to ECR, registers a new ECS task definition, and updates the ECS service.

## Security Notes

- ECR repositories have image scanning enabled on push
- ECR lifecycle policy keeps only the last 10 images
- EFS file system is encrypted at rest with transit encryption (TLS)
- ALB HTTPS listener enforces TLS 1.2+ with `ELBSecurityPolicy-TLS13-1-2-2021-06`
- Stateful resources (ECR, EFS, Cognito, CloudWatch) have `DeletionPolicy: Retain` to prevent accidental data loss
- Deployment circuit breaker enabled with automatic rollback
- `common-parameters.json` is gitignored to prevent committing real AWS resource IDs

### ALB Access Control (without CloudFront)

When CloudFront is not configured, the ALB security group restricts inbound traffic to the deployer's IP address (`/32` CIDR), detected automatically at deploy time.

### ALB Access Control (with CloudFront)

When CloudFront is configured, a defense-in-depth model restricts ALB access:

1. **Security group**: Only allows HTTPS (port 443) from the CloudFront managed prefix list (`com.amazonaws.global.cloudfront.origin-facing`). No CIDR rules, no `0.0.0.0/0`.
2. **WAF WebACL**: Validates a secret `X-Origin-Verify` header on every request. Requests without the correct header are blocked with 403. The secret is stored in SSM Parameter Store and shared between CloudFront (origin custom header) and WAF.
3. **Cognito authentication**: ALB `authenticate-cognito` listener action requires users to log in via Cognito Hosted UI before reaching the application. The user pool is admin-only (no self-registration). Can use a dedicated pool (step 7) or an existing shared pool via `CognitoUserPoolArn` parameters.

### Origin Verify Secret

The deploy script automatically generates a UUID secret on first run and stores it in SSM Parameter Store (`/${PROJECT_NAME}/${ENVIRONMENT}/origin-verify-secret`). On subsequent runs, it retrieves the existing secret. The secret is passed to both the ALB WAF and CloudFront origin as a `NoEcho` parameter.

## Cost Considerations

- **ECR**: Storage costs for Docker images (~$0.10/GB/month)
- **EFS**: Storage costs (~$0.30/GB/month for standard storage)
- **ECS Fargate**: CPU/memory based pricing (~$0.04/vCPU/hour, ~$0.004/GB/hour)
- **ALB**: ~$0.02/hour + data processing charges
- **CloudFront**: ~$0.085/GB data transfer (NA/EU), no minimum commitment
- **WAF**: ~$5/month (WebACL + rule) + $0.60/million requests
- **Cognito**: Free tier covers 50,000 monthly active users
- **Data Transfer**: Minimal costs for in-region transfers
