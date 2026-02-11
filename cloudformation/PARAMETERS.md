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
| **AppDomainName** | Cognito, CloudFront | No | FQDN for the application (enables CloudFront + Cognito) | `app.example.com` | `""` |
| **CognitoDomainPrefix** | Cognito | No | Prefix for Cognito hosted UI domain | `my-app` | `""` |
| **HostedZoneId** | CloudFront | No | Route 53 hosted zone ID for DNS record | `Z0123456789ABC` | `""` |
| **CloudFrontCertificateArn** | CloudFront | No | ACM certificate ARN for CloudFront (must be in us-east-1) | `arn:aws:acm:...` | `""` |
| **CognitoUserPoolArn** | ALB (step 8) | No | ARN of an existing Cognito User Pool to reuse (skips step 7) | `arn:aws:cognito-idp:...` | `""` |
| **CognitoUserPoolClientId** | ALB (step 8) | No | App Client ID from the existing Cognito User Pool | `abc123def456` | `""` |
| **CognitoUserPoolDomain** | ALB (step 8) | No | Full domain of the existing Cognito hosted UI | `prefix.auth.us-east-1.amazoncognito.com` | `""` |

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

The deployment script automatically detects your public IP address and configures the ALB to only accept traffic from your IP with /32 CIDR. When CloudFront is configured, the CIDR rules are replaced by the CloudFront managed prefix list (see below).

### CloudFront + Cognito Configuration (Optional)

There are two ways to enable CloudFront CDN with Cognito authentication:

#### Option A: Create a New Cognito Pool

Set all four of these parameters to create a new Cognito User Pool:

- **AppDomainName** - FQDN for the application (e.g., `app.example.com`). Used as the CloudFront alternate domain name and the Cognito callback URL.
- **CognitoDomainPrefix** - Prefix for the Cognito hosted UI domain. The full domain will be `<prefix>.auth.<region>.amazoncognito.com`. Must be globally unique across all AWS accounts.
- **HostedZoneId** - Route 53 hosted zone ID where the A record alias to CloudFront will be created.
- **CloudFrontCertificateArn** - ACM certificate ARN for CloudFront HTTPS. Must be in us-east-1.

#### Option B: Reuse an Existing Cognito Pool

To skip creating a new Cognito pool (step 7) and reuse an existing one, set these three parameters instead of `CognitoDomainPrefix`:

- **CognitoUserPoolArn** - ARN of the existing Cognito User Pool
- **CognitoUserPoolClientId** - App Client ID configured with callback URL `https://<AppDomainName>/oauth2/idpresponse`
- **CognitoUserPoolDomain** - Full domain of the Cognito hosted UI (e.g., `my-app.auth.us-east-1.amazoncognito.com`)

You must also set `AppDomainName`, `HostedZoneId`, and `CloudFrontCertificateArn` for CloudFront.

Before deploying, create a new App Client in the existing pool:

```bash
aws cognito-idp create-user-pool-client \
  --user-pool-id <pool-id> \
  --client-name "my-app-alb-client" \
  --generate-secret \
  --allowed-o-auth-flows code \
  --allowed-o-auth-flows-user-pool-client \
  --allowed-o-auth-scopes openid \
  --callback-urls "https://<AppDomainName>/oauth2/idpresponse" \
  --supported-identity-providers COGNITO \
  --region us-east-1
```

#### How It Works

The deploy script automatically:

1. Creates a Cognito User Pool (Option A) or uses the existing one (Option B)
2. Looks up the CloudFront managed prefix list (`com.amazonaws.global.cloudfront.origin-facing`)
3. Updates the ALB security group to allow only CloudFront IPs (prefix list on port 443)
4. Creates a WAF WebACL with origin verify header validation
5. Deploys a CloudFront distribution with the custom origin header
6. Creates a Route 53 A record alias to CloudFront

The origin verify secret is auto-generated and stored in SSM Parameter Store.

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
  },
  {
    "ParameterKey": "AppDomainName",
    "ParameterValue": ""
  },
  {
    "ParameterKey": "CognitoDomainPrefix",
    "ParameterValue": ""
  },
  {
    "ParameterKey": "HostedZoneId",
    "ParameterValue": ""
  },
  {
    "ParameterKey": "CloudFrontCertificateArn",
    "ParameterValue": ""
  },
  {
    "ParameterKey": "CognitoUserPoolArn",
    "ParameterValue": ""
  },
  {
    "ParameterKey": "CognitoUserPoolClientId",
    "ParameterValue": ""
  },
  {
    "ParameterKey": "CognitoUserPoolDomain",
    "ParameterValue": ""
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

7. **08-cognito.yaml** - Cognito User Pool (optional, when AppDomainName and CognitoDomainPrefix are set; skipped when CognitoUserPoolArn is provided)
   - Parameters: ProjectName, Environment, AppDomainName, CognitoDomainPrefix

8. **03-load-balancer.yaml** (update) - Adds WAF, Cognito auth, and CloudFront prefix list to ALB
   - Additional parameters: CognitoUserPoolArn, CognitoUserPoolClientId, CognitoUserPoolDomain, OriginVerifyHeaderValue, CloudFrontPrefixListId (all automatic)

9. **09-cloudfront.yaml** - CloudFront distribution and Route 53 DNS (optional, when AppDomainName, HostedZoneId, and CloudFrontCertificateArn are set)
   - Parameters: ProjectName, Environment, AppDomainName, HostedZoneId, CloudFrontCertificateArn, OriginVerifyHeaderValue (automatic)

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
