# CloudFormation Parameters Guide

This guide explains all parameters needed for the AI Image Cropper v2 CloudFormation deployment.

## Quick Start

1. Copy the common parameters file:

   ```bash
   cd cloudformation
   cp common-parameters.json.example common-parameters.json
   ```

2. Update `common-parameters.json` with your AWS resource IDs (see below)

3. Run deployment:

   ```bash
   cd ..
   ./deploy-cloudformation.sh
   ```

The deployment script will automatically extract the relevant parameters for each CloudFormation template from the single `common-parameters.json` file.

## Single Parameters File: common-parameters.json

All deployment parameters are now in one file for easier management. The script automatically filters parameters for each template.

### All Parameters

| Parameter | Used By | Required | Description | Example | Default |
|-----------|---------|----------|-------------|---------|---------|
| **VpcId** | EFS, ALB | Yes | Your VPC ID where resources will be deployed | `vpc-xxxxxxxx` | - |
| **SubnetIds** | EFS, ALB, ECS Service | Yes | Comma-separated list of subnet IDs (minimum 2, recommend 3) | `subnet-xxx,subnet-yyy,subnet-zzz` | - |
| **ECSSecurityGroupId** | EFS, ALB, ECS Service | Yes | Existing security group ID for ECS tasks | `sg-xxxxxxxxxxxxxxxxx` | - |
| **CertificateArn** | ALB | No | ACM certificate ARN for HTTPS. Leave empty for HTTP-only | `arn:aws:acm:...` | `""` |
| **FrontendImageTag** | ECS Service | No | Docker image tag for frontend | `1.0.0` | `1.0.0` |
| **BackendImageTag** | ECS Service | No | Docker image tag for backend | `1.0.0` | `1.0.0` |
| **TaskCpu** | ECS Service | No | CPU units for ECS task (1024 = 1 vCPU) | `2048` | `2048` |
| **TaskMemory** | ECS Service | No | Memory in MB for ECS task | `4096` | `4096` |
| **DesiredCount** | ECS Service | No | Number of ECS tasks to run | `1` | `1` |

### How to Find AWS Resource IDs

```bash
# Find your VPC ID
aws ec2 describe-vpcs --region us-east-1

# Find subnets in your VPC
aws ec2 describe-subnets --filters "Name=vpc-id,Values=vpc-xxxxxxxx" --region us-east-1

# Find or create security group for ECS
aws ec2 describe-security-groups --filters "Name=vpc-id,Values=vpc-xxxxxxxx" --region us-east-1

# Find ACM certificates (optional for HTTPS)
aws acm list-certificates --region us-east-1
```

## Parameter Details

### Network Configuration

#### VpcId, SubnetIds, ECSSecurityGroupId

These three parameters define the network infrastructure where your application will run. They must all be from the same VPC.

#### Subnet Requirements

- **EFS**: Requires at least 2 subnets in different availability zones
- **ALB**: Requires at least 2 public subnets in different availability zones
- **ECS Service**: Can use private subnets (with NAT gateway) or public subnets

#### Security Group Rules Required

- Ingress: Port 2049 (NFS) from ECS tasks for EFS
- Ingress: Port 80 from ALB for ECS tasks
- Ingress: Port 8000 from frontend container for backend container
- Egress: All traffic (for pulling Docker images, downloading AI models, etc.)

### HTTPS Configuration (Optional)

#### CertificateArn

For production deployments, you can add HTTPS support:

- Leave empty (`""`) for HTTP-only deployment
- Request an ACM certificate for your domain
- Certificate must be in the same region as deployment (us-east-1)
- After deployment, create a CNAME record pointing your domain to the ALB DNS

#### AllowedCidr (Automatic)

The deployment script automatically detects your public IP address and configures the ALB to only accept traffic from your IP with /32 CIDR.

**How it works:**

- Script queries AWS checkip service to get your current public IP
- Automatically sets ALB security group to `YOUR.IP.ADD.RESS/32`
- Provides better security by restricting access to only your location
- No manual configuration needed

**If you need different access:**

- To allow from multiple IPs, you'll need to manually update the ALB security group after deployment
- To allow public access (not recommended), manually update the security group to `0.0.0.0/0`

### ECS Task Configuration

#### TaskCpu and TaskMemory

Valid Fargate CPU/Memory combinations:

- 256 CPU: 512, 1024, 2048 MB
- 512 CPU: 1024-4096 MB (1GB increments)
- 1024 CPU: 2048-8192 MB (1GB increments)
- 2048 CPU: 4096-16384 MB (1GB increments)
- 4096 CPU: 8192-30720 MB (1GB increments)

#### Recommended for AI Image Cropper

- Development: 1024 CPU / 2048 MB
- Production: 2048 CPU / 4096 MB (default)
- Heavy workload: 4096 CPU / 8192 MB

#### Image Tags

The `FrontendImageTag` and `BackendImageTag` parameters specify which Docker image versions to deploy:

- `1.0.0` - Specific version tag (recommended)
- `latest` - Always use the most recent image (not recommended for production)
- Custom tags like `v1.2.3`, `prod`, `staging`

#### DesiredCount

Number of ECS task instances to run:

- `1` - Single instance (default, good for development)
- `2+` - Multiple instances for high availability

## Example Configuration

Here's a complete example configuration file:

**cloudformation/common-parameters.json:**

```json
[
  {
    "ParameterKey": "VpcId",
    "ParameterValue": "vpc-xxxxxxxx"
  },
  {
    "ParameterKey": "SubnetIds",
    "ParameterValue": "subnet-xxxxxxxx,subnet-yyyyyyyy,subnet-zzzzzzzz"
  },
  {
    "ParameterKey": "ECSSecurityGroupId",
    "ParameterValue": "sg-xxxxxxxxxxxxxxxxx"
  },
  {
    "ParameterKey": "CertificateArn",
    "ParameterValue": ""
  },
  {
    "ParameterKey": "FrontendImageTag",
    "ParameterValue": "1.0.0"
  },
  {
    "ParameterKey": "BackendImageTag",
    "ParameterValue": "1.0.0"
  },
  {
    "ParameterKey": "TaskCpu",
    "ParameterValue": "2048"
  },
  {
    "ParameterKey": "TaskMemory",
    "ParameterValue": "4096"
  },
  {
    "ParameterKey": "DesiredCount",
    "ParameterValue": "1"
  }
]
```

## Deployment Order

The deployment script automatically handles the correct template order:

1. **01-ecr-repositories.yaml** - Container image repositories
   - Parameters: ProjectName, Environment (automatic)

2. **02-efs-storage.yaml** - Elastic File System
   - Parameters: ProjectName, Environment, VpcId, SubnetIds, ECSSecurityGroupId

3. **03-load-balancer.yaml** - Application Load Balancer
   - Parameters: ProjectName, Environment, VpcId, SubnetIds, CertificateArn, AllowedCidr (automatic), ECSSecurityGroupId

4. **04-iam-roles.yaml** - IAM roles and policies
   - Parameters: ProjectName, Environment (automatic)

5. **05-ecs-cluster.yaml** - ECS cluster and CloudWatch logs
   - Parameters: ProjectName, Environment (automatic)

6. **06-ecs-service.yaml** - ECS service and task definition
   - Parameters: ProjectName, Environment, SubnetIds, ECSSecurityGroupId, FrontendImageTag, BackendImageTag, TaskCpu, TaskMemory, DesiredCount

## First Deployment Workflow

For a first-time deployment, follow this workflow:

1. Create `common-parameters.json` with your AWS resource IDs
2. Run `./deploy-cloudformation.sh` - This deploys infrastructure (steps 1-5)
3. Build and push Docker images: `./update_ecs_task.sh`
4. Run `./deploy-cloudformation.sh` again - This deploys the ECS service (step 6)

Alternatively, you can build and push images first, then run the deployment script once.

## Updating Parameters After Deployment

To update any parameter after initial deployment:

1. Edit `cloudformation/common-parameters.json`
2. Run `./deploy-cloudformation.sh` again
3. The script will update only the affected stacks

**Note:** The script automatically skips stacks that are already successfully deployed and haven't changed. It will only update stacks whose parameters or templates have been modified.

## Parameters Automatically Provided

The following parameters are automatically provided by the deployment script and do NOT need to be in `common-parameters.json`:

- **ProjectName**: `ai-image-cropper-v2` (configured in script)
- **Environment**: `prod` (configured in script)
- **AWS Region**: All resources are deployed in the same region (configured in script)

To change these, edit the variables at the top of `deploy-cloudformation.sh`:

```bash
PROJECT_NAME="ai-image-cropper-v2"
ENVIRONMENT="prod"
REGION="us-east-1"
```

**Important:** All AWS resources (ECR, EFS, ALB, ECS, etc.) are automatically deployed in the same region specified by the `REGION` variable. This ensures consistency and proper communication between services. The backend and frontend containers both run in the same region as the ECS cluster.

## Troubleshooting

### Invalid Parameter Combination

**Error:** "Invalid CPU and Memory combination"

**Solution:** Check the valid Fargate combinations listed above. Common mistake is pairing 2048 CPU with 2048 MB (not allowed).

### Stack Update No Changes

**Message:** "No updates to be performed on stack"

This is normal - it means the stack is already in the desired state.

### Missing VPC or Subnet

**Error:** "The subnet ID 'subnet-xxx' does not exist"

**Solution:**

- Verify the subnet IDs exist in your account: `aws ec2 describe-subnets --region us-east-1`
- Ensure subnets are in the same VPC as VpcId
- Check for typos in the subnet IDs

### Security Group Issues

**Error:** "The security group 'sg-xxx' does not exist"

**Solution:**

- Create a security group in your VPC
- Add required ingress/egress rules (see Security Group Rules Required above)
- Update `ECSSecurityGroupId` in `common-parameters.json`
