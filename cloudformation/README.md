# CloudFormation Deployment

This directory contains CloudFormation templates and deployment scripts for the AI Image Cropper v2 infrastructure on AWS.

## Prerequisites

- AWS CLI installed and configured
- AWS credentials with CloudFormation, ECR, EFS, and IAM permissions
- Bash shell

## Files

- `01-ecr-repositories.yaml` - Creates ECR repositories for frontend and backend images
- `02-efs-storage.yaml` - Creates EFS file system for shared storage
- `deploy-cloudformation.sh` - Automated deployment script for both stacks
- `update_ecs_task.sh` - Script to build, push Docker images and update ECS tasks
- `efs-parameters.json.example` - Example parameters file for EFS deployment

## Quick Start

### 1. Deploy ECR Repositories Only

```bash
cd cloudfront
./deploy-cloudformation.sh
```

The script will:
- Deploy the ECR repositories stack
- Skip EFS deployment if `efs-parameters.json` doesn't exist
- Display outputs including ECR repository URIs

### 2. Deploy ECR + EFS (Full Infrastructure)

First, create your EFS parameters file:

```bash
cp efs-parameters.json.example efs-parameters.json
```

Edit `efs-parameters.json` with your VPC details:

```json
[
  {
    "ParameterKey": "VpcId",
    "ParameterValue": "vpc-0123456789abcdef0"
  },
  {
    "ParameterKey": "SubnetIds",
    "ParameterValue": "subnet-abc123,subnet-def456"
  },
  {
    "ParameterKey": "ECSSecurityGroupId",
    "ParameterValue": "sg-0123456789abcdef0"
  }
]
```

Then run the deployment:

```bash
./deploy-cloudformation.sh
```

## Configuration

Edit the variables at the top of `deploy-cloudformation.sh`:

```bash
PROJECT_NAME="ai-image-cropper-v2"
ENVIRONMENT="prod"              # Options: dev, staging, prod
REGION="us-east-1"
```

## Stack Names

The script creates stacks with the following naming convention:

- ECR: `${PROJECT_NAME}-ecr-${ENVIRONMENT}`
- EFS: `${PROJECT_NAME}-efs-${ENVIRONMENT}`

Default names:
- `ai-image-cropper-v2-ecr-prod`
- `ai-image-cropper-v2-efs-prod`

## Outputs

### ECR Stack Outputs

- **FrontendECRRepository**: URI of the frontend ECR repository
- **BackendECRRepository**: URI of the backend ECR repository
- **FrontendRepositoryName**: Name of the frontend repository
- **BackendRepositoryName**: Name of the backend repository

### EFS Stack Outputs

- **EFSFileSystemId**: ID of the EFS file system
- **EFSSecurityGroupId**: ID of the EFS security group

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
    file://efs-parameters.json \
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

To remove all infrastructure:

```bash
# Delete in reverse order
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

## Next Steps

After successful deployment:

1. **Build and push Docker images**:
   ```bash
   ./update_ecs_task.sh
   ```

2. **Deploy ECS cluster, task definition, and service** (requires additional CloudFormation templates)

3. **Configure Application Load Balancer** (if not already created)

4. **Set up DNS records** for your domain

## Security Notes

- ECR repositories have image scanning enabled on push
- ECR lifecycle policy keeps only the last 10 images
- EFS file system is encrypted at rest
- EFS uses transit encryption (TLS)
- Security groups restrict EFS access to ECS tasks only

## Cost Considerations

- **ECR**: Storage costs for Docker images (~$0.10/GB/month)
- **EFS**: Storage costs (~$0.30/GB/month for standard storage)
- **Data Transfer**: Minimal costs for in-region transfers

Estimated monthly cost: $5-20 depending on image sizes and storage usage
