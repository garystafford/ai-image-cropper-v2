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
- `03-load-balancer.yaml` - Application Load Balancer with HTTP/HTTPS listeners
- `04-iam-roles.yaml` - IAM execution and task roles for ECS
- `05-ecs-cluster.yaml` - ECS Fargate cluster and CloudWatch log group
- `06-ecs-service.yaml` - ECS service and task definition
- `07-ecs-application.yaml` - Alternate combined application template

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

The script will deploy all 6 CloudFormation stacks in order, automatically detecting whether to create or update each stack.

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

**Warning**: Deleting the ECR stack will also delete all container images stored in the repositories.

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
- ALB security group restricts access to deployer's IP address
- Deployment circuit breaker enabled with automatic rollback
- `common-parameters.json` is gitignored to prevent committing real AWS resource IDs

## Cost Considerations

- **ECR**: Storage costs for Docker images (~$0.10/GB/month)
- **EFS**: Storage costs (~$0.30/GB/month for standard storage)
- **ECS Fargate**: CPU/memory based pricing (~$0.04/vCPU/hour, ~$0.004/GB/hour)
- **ALB**: ~$0.02/hour + data processing charges
- **Data Transfer**: Minimal costs for in-region transfers
