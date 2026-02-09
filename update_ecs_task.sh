#!/bin/bash
# shellcheck disable=SC2016  # Backticks in single quotes are intentional JMESPath syntax for AWS CLI

set -e  # Exit on error

# Configuration
PROJECT_NAME="ai-image-cropper-v2"
ENVIRONMENT="prod"
REGION="us-east-1"
PARAMS_FILE="cloudformation/common-parameters.json"

# Get AWS account ID
ACCOUNT=$(aws sts get-caller-identity --query "Account" --output text)

# Get image tags from common-parameters.json
FRONTEND_TAG=$(grep -A 1 "FrontendImageTag" "$PARAMS_FILE" | grep "ParameterValue" | sed 's/.*"ParameterValue": "\(.*\)".*/\1/')
BACKEND_TAG=$(grep -A 1 "BackendImageTag" "$PARAMS_FILE" | grep "ParameterValue" | sed 's/.*"ParameterValue": "\(.*\)".*/\1/')

# Get values from CloudFormation stack outputs
EFS_ID=$(aws cloudformation describe-stacks \
    --stack-name "${PROJECT_NAME}-efs-${ENVIRONMENT}" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`EFSFileSystemId`].OutputValue' \
    --output text)

CLUSTER=$(aws cloudformation describe-stacks \
    --stack-name "${PROJECT_NAME}-cluster-${ENVIRONMENT}" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`ECSClusterName`].OutputValue' \
    --output text)

# Get execution and task role ARNs from IAM stack
EXECUTION_ROLE_ARN=$(aws cloudformation describe-stacks \
    --stack-name "${PROJECT_NAME}-iam-${ENVIRONMENT}" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`TaskExecutionRoleArn`].OutputValue' \
    --output text)

TASK_ROLE_ARN=$(aws cloudformation describe-stacks \
    --stack-name "${PROJECT_NAME}-iam-${ENVIRONMENT}" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`TaskRoleArn`].OutputValue' \
    --output text)

# Get log group name from cluster stack
LOG_GROUP=$(aws cloudformation describe-stacks \
    --stack-name "${PROJECT_NAME}-cluster-${ENVIRONMENT}" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`LogGroupName`].OutputValue' \
    --output text)

# Get SubnetIds and ECSSecurityGroupId from common-parameters.json
SUBNETS=$(grep -A 1 "SubnetIds" "$PARAMS_FILE" | grep "ParameterValue" | sed 's/.*"ParameterValue": "\(.*\)".*/\1/')
ECS_SG=$(grep -A 1 "ECSSecurityGroupId" "$PARAMS_FILE" | grep "ParameterValue" | sed 's/.*"ParameterValue": "\(.*\)".*/\1/')

# Get ECR repository names from ECR stack
FRONTEND_REPO=$(aws cloudformation describe-stacks \
    --stack-name "${PROJECT_NAME}-ecr-${ENVIRONMENT}" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`FrontendRepositoryName`].OutputValue' \
    --output text)

BACKEND_REPO=$(aws cloudformation describe-stacks \
    --stack-name "${PROJECT_NAME}-ecr-${ENVIRONMENT}" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`BackendRepositoryName`].OutputValue' \
    --output text)

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to check if image tag exists in ECR
image_exists_in_ecr() {
    local repo_name=$1
    local image_tag=$2

    if aws ecr describe-images \
        --repository-name "$repo_name" \
        --image-ids imageTag="$image_tag" \
        --region "$REGION" \
        --output text &>/dev/null; then
        return 0
    else
        return 1
    fi
}

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}AI Image Cropper v2 - Build and Deploy${NC}"
echo -e "${BLUE}========================================${NC}"

# Validate retrieved values
echo -e "\n${BLUE}Configuration:${NC}"
echo -e "${YELLOW}Project:${NC} ${PROJECT_NAME}"
echo -e "${YELLOW}Environment:${NC} ${ENVIRONMENT}"
echo -e "${YELLOW}Region:${NC} ${REGION}"
echo -e "${YELLOW}Account:${NC} ${ACCOUNT}"
echo -e "\n${BLUE}From CloudFormation Stacks:${NC}"
echo -e "${YELLOW}Frontend Repo:${NC} ${FRONTEND_REPO}"
echo -e "${YELLOW}Backend Repo:${NC} ${BACKEND_REPO}"
echo -e "${YELLOW}EFS ID:${NC} ${EFS_ID}"
echo -e "${YELLOW}Cluster:${NC} ${CLUSTER}"
echo -e "${YELLOW}Log Group:${NC} ${LOG_GROUP}"
echo -e "${YELLOW}Execution Role:${NC} ${EXECUTION_ROLE_ARN}"
echo -e "${YELLOW}Task Role:${NC} ${TASK_ROLE_ARN}"
echo -e "\n${BLUE}From Parameters File:${NC}"
echo -e "${YELLOW}Frontend Tag:${NC} ${FRONTEND_TAG}"
echo -e "${YELLOW}Backend Tag:${NC} ${BACKEND_TAG}"
echo -e "${YELLOW}Task CPU:${NC} ${TASK_CPU}"
echo -e "${YELLOW}Task Memory:${NC} ${TASK_MEMORY} MB"
echo -e "${YELLOW}Subnets:${NC} ${SUBNETS}"
echo -e "${YELLOW}Security Group:${NC} ${ECS_SG}"

# Validate required values
if [[ -z "$EFS_ID" ]] || [[ -z "$CLUSTER" ]] || [[ -z "$FRONTEND_REPO" ]] || [[ -z "$BACKEND_REPO" ]]; then
    echo -e "\n${RED}✗ Error: Failed to retrieve required values from CloudFormation stacks${NC}"
    echo -e "${RED}Please ensure all CloudFormation stacks are deployed successfully${NC}"
    exit 1
fi

# Authenticate Docker to ECR
echo -e "\n${YELLOW}Authenticating Docker to ECR...${NC}"
aws ecr get-login-password --region "${REGION}" | docker login --username AWS --password-stdin "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"

# Build, tag, and push Backend Docker image
echo -e "\n${BLUE}Processing Backend Image (tag: ${BACKEND_TAG})${NC}"
if image_exists_in_ecr "${BACKEND_REPO}" "${BACKEND_TAG}"; then
    echo -e "${GREEN}✓ Backend image ${BACKEND_TAG} already exists in ECR. Skipping build and push.${NC}"
else
    echo -e "${YELLOW}Building backend image...${NC}"
    docker build --platform linux/amd64 -t "${BACKEND_REPO}:${BACKEND_TAG}" -f Dockerfile.backend .
    echo -e "${YELLOW}Tagging backend image...${NC}"
    docker tag "${BACKEND_REPO}:${BACKEND_TAG}" "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${BACKEND_REPO}:${BACKEND_TAG}"
    echo -e "${YELLOW}Pushing backend image to ECR...${NC}"
    docker push "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${BACKEND_REPO}:${BACKEND_TAG}"
    echo -e "${GREEN}✓ Backend image pushed successfully${NC}"
fi

# Build, tag, and push Frontend Docker image
echo -e "\n${BLUE}Processing Frontend Image (tag: ${FRONTEND_TAG})${NC}"
if image_exists_in_ecr "${FRONTEND_REPO}" "${FRONTEND_TAG}"; then
    echo -e "${GREEN}✓ Frontend image ${FRONTEND_TAG} already exists in ECR. Skipping build and push.${NC}"
else
    echo -e "${YELLOW}Building frontend image...${NC}"
    docker build --platform linux/amd64 -f Dockerfile.frontend -t "${FRONTEND_REPO}:${FRONTEND_TAG}" .
    echo -e "${YELLOW}Tagging frontend image...${NC}"
    docker tag "${FRONTEND_REPO}:${FRONTEND_TAG}" "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${FRONTEND_REPO}:${FRONTEND_TAG}"
    echo -e "${YELLOW}Pushing frontend image to ECR...${NC}"
    docker push "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${FRONTEND_REPO}:${FRONTEND_TAG}"
    echo -e "${GREEN}✓ Frontend image pushed successfully${NC}"
fi

# Get CPU and Memory from common-parameters.json
TASK_CPU=$(grep -A 1 "TaskCpu" "$PARAMS_FILE" | grep "ParameterValue" | sed 's/.*"ParameterValue": "\(.*\)".*/\1/')
TASK_MEMORY=$(grep -A 1 "TaskMemory" "$PARAMS_FILE" | grep "ParameterValue" | sed 's/.*"ParameterValue": "\(.*\)".*/\1/')

# Register ECS task definition (creates new revision each time)
echo -e "\n${BLUE}Registering ECS Task Definition...${NC}"
CONTAINER_DEFS=$(cat <<EOF
[
  {
    "name": "frontend",
    "image": "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${FRONTEND_REPO}:${FRONTEND_TAG}",
    "portMappings": [
      {
        "containerPort": 80,
        "hostPort": 80,
        "protocol": "tcp"
      }
    ],
    "essential": true,
    "environment": [
      {
        "name": "BACKEND_HOST",
        "value": "127.0.0.1"
      }
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "${LOG_GROUP}",
        "awslogs-region": "${REGION}",
        "awslogs-stream-prefix": "frontend"
      }
    }
  },
  {
    "name": "backend",
    "image": "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${BACKEND_REPO}:${BACKEND_TAG}",
    "portMappings": [
      {
        "containerPort": 8000,
        "hostPort": 8000,
        "protocol": "tcp"
      }
    ],
    "essential": true,
    "mountPoints": [
      {
        "sourceVolume": "efs-storage",
        "containerPath": "/app/data",
        "readOnly": false
      }
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "${LOG_GROUP}",
        "awslogs-region": "${REGION}",
        "awslogs-stream-prefix": "backend"
      }
    }
  }
]
EOF
)

TASK_DEF_ARN=$(aws ecs register-task-definition \
  --family "${PROJECT_NAME}-task-${ENVIRONMENT}" \
  --network-mode awsvpc \
  --requires-compatibilities FARGATE \
  --cpu "${TASK_CPU}" \
  --memory "${TASK_MEMORY}" \
  --execution-role-arn "${EXECUTION_ROLE_ARN}" \
  --task-role-arn "${TASK_ROLE_ARN}" \
  --container-definitions "$CONTAINER_DEFS" \
  --volumes "[{\"name\":\"efs-storage\",\"efsVolumeConfiguration\":{\"fileSystemId\":\"${EFS_ID}\",\"transitEncryption\":\"ENABLED\"}}]" \
  --region "${REGION}" \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text)

echo -e "${GREEN}✓ Task definition registered: ${TASK_DEF_ARN}${NC}"

# Get service name from CloudFormation (if it exists)
SERVICE_NAME=$(aws cloudformation describe-stacks \
    --stack-name "${PROJECT_NAME}-service-${ENVIRONMENT}" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`ECSServiceName`].OutputValue' \
    --output text 2>/dev/null || echo "")

# Update service to use new task definition with ALB configuration (redeploys each time)
if [[ -n "$SERVICE_NAME" ]]; then
    echo -e "\n${BLUE}Updating ECS Service...${NC}"
    echo -e "${YELLOW}Cluster: ${CLUSTER}${NC}"
    echo -e "${YELLOW}Service: ${SERVICE_NAME}${NC}"
    aws ecs update-service \
      --cluster "${CLUSTER}" \
      --service "${SERVICE_NAME}" \
      --task-definition "${TASK_DEF_ARN}" \
      --force-new-deployment \
      --health-check-grace-period-seconds 60 \
      --region "${REGION}" \
      --query 'service.serviceName' \
      --output text >/dev/null

    echo -e "${GREEN}✓ Service update initiated${NC}"
    echo -e "\n${YELLOW}Waiting for service to stabilize (this may take a few minutes)...${NC}"
    if aws ecs wait services-stable \
      --cluster "${CLUSTER}" \
      --services "${SERVICE_NAME}" \
      --region "${REGION}"; then
        echo -e "${GREEN}✓ Service stabilized successfully${NC}"
    else
        echo -e "${YELLOW}⚠ Service stabilization timed out, check manually${NC}"
    fi
else
    echo -e "\n${YELLOW}⚠ ECS Service not yet deployed${NC}"
    echo -e "${YELLOW}Task definition registered but service does not exist yet.${NC}"
    echo -e "${YELLOW}Run './deploy-cloudformation.sh' to deploy the ECS service (step 6)${NC}"
fi

echo -e "\n${BLUE}========================================${NC}"
echo -e "${GREEN}✓ Deployment Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
