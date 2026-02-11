#!/bin/bash

# AI Image Cropper v2 - CloudFormation Deployment Script
# Deploys complete AWS infrastructure for AI Image Cropper application
# Run from project root directory

set -eo pipefail  # Exit on error, fail on pipe errors

# ========================================
# Configuration
# ========================================
PROJECT_NAME="ai-image-cropper-v2"
ENVIRONMENT="prod"
REGION="us-east-1"

# Template directory
TEMPLATE_DIR="cloudformation"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ========================================
# Functions
# ========================================
print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

wait_for_stack() {
    local stack_name=$1
    local operation=$2

    print_info "Waiting for stack $stack_name to complete $operation..."

    if aws cloudformation wait "stack-${operation}-complete" \
        --stack-name "$stack_name" \
        --region "$REGION" 2>/dev/null; then
        print_success "Stack $stack_name $operation completed successfully"
        return 0
    else
        print_error "Stack $stack_name $operation failed or timed out"
        return 1
    fi
}

get_stack_outputs() {
    local stack_name=$1

    echo -e "\n${BLUE}Stack Outputs:${NC}"
    aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
        --output table
}

check_stack_exists() {
    local stack_name=$1

    if aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$REGION" &>/dev/null; then
        return 0
    else
        return 1
    fi
}

get_stack_status() {
    local stack_name=$1

    aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null
}

is_stack_complete() {
    local stack_name=$1
    local status
    status=$(get_stack_status "$stack_name")

    if [[ "$status" == "CREATE_COMPLETE" ]] || [[ "$status" == "UPDATE_COMPLETE" ]]; then
        return 0
    else
        return 1
    fi
}

# Create parameters file with ProjectName, Environment, and filtered common parameters
create_params_file() {
    local temp_file
    temp_file=$(mktemp)
    local param_keys=("$@")

    # Start with ProjectName and Environment
    cat > "$temp_file" <<EOF
[
  {
    "ParameterKey": "ProjectName",
    "ParameterValue": "$PROJECT_NAME"
  },
  {
    "ParameterKey": "Environment",
    "ParameterValue": "$ENVIRONMENT"
  }
EOF

    # Add comma if we have additional parameters
    if [[ ${#param_keys[@]} -gt 0 ]]; then
        echo "," >> "$temp_file"

        # Extract and filter parameters from common file
        local first=true
        for key in "${param_keys[@]}"; do
            # Find the parameter in common-parameters.json
            local param_block
            param_block=$(grep -A 1 "\"ParameterKey\": \"$key\"" "$TEMPLATE_DIR/common-parameters.json" | grep -A 1 "ParameterKey")

            if [[ -n "$param_block" ]]; then
                if [[ "$first" == false ]]; then
                    echo "," >> "$temp_file"
                fi
                first=false

                # Extract the value
                local value
                value=$(grep -A 1 "\"ParameterKey\": \"$key\"" "$TEMPLATE_DIR/common-parameters.json" | grep "ParameterValue" | sed 's/.*"ParameterValue": "\(.*\)".*/\1/')

                # Write parameter to temp file
                cat >> "$temp_file" <<EOF
  {
    "ParameterKey": "$key",
    "ParameterValue": "$value"
  }
EOF
            fi
        done
    fi

    # Close JSON array
    echo "]" >> "$temp_file"

    echo "$temp_file"
}

# Get current public IP address
get_public_ip() {
    local ip

    # Try multiple services for reliability
    ip=$(curl -s --max-time 5 https://checkip.amazonaws.com 2>/dev/null) || \
    ip=$(curl -s --max-time 5 https://api.ipify.org 2>/dev/null) || \
    ip=$(curl -s --max-time 5 https://icanhazip.com 2>/dev/null)

    if [[ -z "$ip" ]]; then
        print_error "Failed to detect public IP address"
        echo ""
        echo "Please manually specify your IP address or use 0.0.0.0/0 for public access"
        exit 1
    fi

    echo "$ip"
}

# ========================================
# Validation
# ========================================
if [[ ! -d "$TEMPLATE_DIR" ]]; then
    print_error "Template directory '$TEMPLATE_DIR' not found!"
    print_info "Please run this script from the project root directory."
    exit 1
fi

if [[ ! -f "$TEMPLATE_DIR/01-ecr-repositories.yaml" ]]; then
    print_error "CloudFormation template not found: $TEMPLATE_DIR/01-ecr-repositories.yaml"
    exit 1
fi

if [[ ! -f "$TEMPLATE_DIR/02-efs-storage.yaml" ]]; then
    print_error "CloudFormation template not found: $TEMPLATE_DIR/02-efs-storage.yaml"
    exit 1
fi

if [[ ! -f "$TEMPLATE_DIR/03-load-balancer.yaml" ]]; then
    print_error "CloudFormation template not found: $TEMPLATE_DIR/03-load-balancer.yaml"
    exit 1
fi

if [[ ! -f "$TEMPLATE_DIR/04-iam-roles.yaml" ]]; then
    print_error "CloudFormation template not found: $TEMPLATE_DIR/04-iam-roles.yaml"
    exit 1
fi

if [[ ! -f "$TEMPLATE_DIR/05-ecs-cluster.yaml" ]]; then
    print_error "CloudFormation template not found: $TEMPLATE_DIR/05-ecs-cluster.yaml"
    exit 1
fi

if [[ ! -f "$TEMPLATE_DIR/06-ecs-service.yaml" ]]; then
    print_error "CloudFormation template not found: $TEMPLATE_DIR/06-ecs-service.yaml"
    exit 1
fi

# Check for common parameters file
if [[ ! -f "$TEMPLATE_DIR/common-parameters.json" ]]; then
    print_error "Missing $TEMPLATE_DIR/common-parameters.json file!"
    echo ""
    echo "Please create $TEMPLATE_DIR/common-parameters.json with all required parameters."
    echo "You can copy the example: cp $TEMPLATE_DIR/common-parameters.json.example $TEMPLATE_DIR/common-parameters.json"
    echo ""
    exit 1
fi

# Helper to extract a parameter value from common-parameters.json
get_param_value() {
    local key=$1
    grep -A 1 "\"ParameterKey\": \"$key\"" "$TEMPLATE_DIR/common-parameters.json" \
        | grep "ParameterValue" \
        | sed 's/.*"ParameterValue": "\(.*\)".*/\1/'
}

# ========================================
# Detect optional Cognito/CloudFront configuration
# ========================================
ENABLE_COGNITO=false
ENABLE_CLOUDFRONT=false
USE_EXISTING_COGNITO=false

COGNITO_DOMAIN_PREFIX=$(get_param_value "CognitoDomainPrefix")
APP_DOMAIN_NAME=$(get_param_value "AppDomainName")
HOSTED_ZONE_ID=$(get_param_value "HostedZoneId")
CF_CERT_ARN=$(get_param_value "CloudFrontCertificateArn")

# Check for pre-existing Cognito pool parameters (reuse existing pool)
EXISTING_COGNITO_ARN=$(get_param_value "CognitoUserPoolArn")
EXISTING_COGNITO_CLIENT_ID=$(get_param_value "CognitoUserPoolClientId")
EXISTING_COGNITO_DOMAIN=$(get_param_value "CognitoUserPoolDomain")

if [[ -n "$EXISTING_COGNITO_ARN" && -n "$EXISTING_COGNITO_CLIENT_ID" && -n "$EXISTING_COGNITO_DOMAIN" ]]; then
    # Reuse an existing Cognito User Pool (skip step 7)
    USE_EXISTING_COGNITO=true
    ENABLE_COGNITO=true
elif [[ -n "$COGNITO_DOMAIN_PREFIX" && -n "$APP_DOMAIN_NAME" ]]; then
    # Create a new Cognito User Pool via CloudFormation (step 7)
    ENABLE_COGNITO=true
fi

if [[ -n "$APP_DOMAIN_NAME" && -n "$HOSTED_ZONE_ID" && -n "$CF_CERT_ARN" ]]; then
    ENABLE_CLOUDFRONT=true
fi

# Validate optional templates if features are enabled
if [[ "$ENABLE_COGNITO" == true && "$USE_EXISTING_COGNITO" == false ]]; then
    if [[ ! -f "$TEMPLATE_DIR/08-cognito.yaml" ]]; then
        print_error "CloudFormation template not found: $TEMPLATE_DIR/08-cognito.yaml"
        exit 1
    fi
fi

if [[ "$ENABLE_CLOUDFRONT" == true ]]; then
    if [[ ! -f "$TEMPLATE_DIR/09-cloudfront.yaml" ]]; then
        print_error "CloudFormation template not found: $TEMPLATE_DIR/09-cloudfront.yaml"
        exit 1
    fi
fi

# ========================================
# Main Deployment Logic
# ========================================

print_header "AI Image Cropper v2 - CloudFormation Deployment"

echo "Project: $PROJECT_NAME"
echo "Environment: $ENVIRONMENT"
echo "Region: $REGION"
echo "Templates: $TEMPLATE_DIR/"
if [[ "$USE_EXISTING_COGNITO" == true ]]; then
    print_info "Cognito authentication enabled (reusing existing pool: $EXISTING_COGNITO_ARN)"
elif [[ "$ENABLE_COGNITO" == true ]]; then
    print_info "Cognito authentication enabled (new pool, domain prefix: $COGNITO_DOMAIN_PREFIX)"
fi
if [[ "$ENABLE_CLOUDFRONT" == true ]]; then
    print_info "CloudFront distribution enabled (domain: $APP_DOMAIN_NAME)"
fi
echo ""

# ========================================
# Step 1: Deploy ECR Repositories
# ========================================
STACK_NAME_ECR="${PROJECT_NAME}-ecr-${ENVIRONMENT}"

print_header "Step 1: Deploying ECR Repositories"

OPERATION=""

if check_stack_exists "$STACK_NAME_ECR"; then
    CURRENT_STATUS=$(get_stack_status "$STACK_NAME_ECR")
    print_info "Stack $STACK_NAME_ECR exists with status: $CURRENT_STATUS"

    if is_stack_complete "$STACK_NAME_ECR"; then
        print_success "Stack $STACK_NAME_ECR is already in a completed state. Skipping deployment."
    else
        print_info "Stack $STACK_NAME_ECR needs updating..."
        OPERATION="update"

        aws cloudformation update-stack \
            --stack-name "$STACK_NAME_ECR" \
            --template-body "file://$TEMPLATE_DIR/01-ecr-repositories.yaml" \
            --parameters \
                ParameterKey=ProjectName,ParameterValue="$PROJECT_NAME" \
                ParameterKey=Environment,ParameterValue="$ENVIRONMENT" \
            --region "$REGION" \
            --capabilities CAPABILITY_IAM \
            2>/dev/null || {
                if [[ $? -eq 254 ]]; then
                    print_info "No updates to be performed on $STACK_NAME_ECR"
                    OPERATION=""
                else
                    print_error "Failed to update stack $STACK_NAME_ECR"
                    exit 1
                fi
            }
    fi
else
    print_info "Creating stack $STACK_NAME_ECR..."
    OPERATION="create"

    aws cloudformation create-stack \
        --stack-name "$STACK_NAME_ECR" \
        --template-body "file://$TEMPLATE_DIR/01-ecr-repositories.yaml" \
        --parameters \
            ParameterKey=ProjectName,ParameterValue="$PROJECT_NAME" \
            ParameterKey=Environment,ParameterValue="$ENVIRONMENT" \
        --region "$REGION" \
        --capabilities CAPABILITY_IAM
fi

# Wait for ECR stack to complete
if [[ "$OPERATION" != "" ]]; then
    if ! wait_for_stack "$STACK_NAME_ECR" "$OPERATION"; then
        print_error "ECR stack deployment failed. Check AWS Console for details."
        exit 1
    fi
fi

# Display ECR outputs
get_stack_outputs "$STACK_NAME_ECR"

# ========================================
# Step 2: Deploy EFS Storage
# ========================================
STACK_NAME_EFS="${PROJECT_NAME}-efs-${ENVIRONMENT}"

print_header "Step 2: Deploying EFS Storage"

print_info "Using parameters from $TEMPLATE_DIR/common-parameters.json"

# Create parameters file with EFS-specific parameters
TEMP_PARAMS_FILE=$(create_params_file "VpcId" "SubnetIds" "ECSSecurityGroupId")

# Cleanup function to remove temp files
cleanup_temp() {
    rm -f "$TEMP_PARAMS_FILE" "$TEMP_ALB_PARAMS_FILE" "$TEMP_ECS_PARAMS_FILE" \
          "$TEMP_COGNITO_PARAMS_FILE" "$TEMP_ALB_UPDATE_PARAMS_FILE" "$TEMP_CF_PARAMS_FILE"
}
trap cleanup_temp EXIT

OPERATION=""

if check_stack_exists "$STACK_NAME_EFS"; then
    CURRENT_STATUS=$(get_stack_status "$STACK_NAME_EFS")
    print_info "Stack $STACK_NAME_EFS exists with status: $CURRENT_STATUS"

    if is_stack_complete "$STACK_NAME_EFS"; then
        print_success "Stack $STACK_NAME_EFS is already in a completed state. Skipping deployment."
    else
        print_info "Stack $STACK_NAME_EFS needs updating..."
        OPERATION="update"

        aws cloudformation update-stack \
            --stack-name "$STACK_NAME_EFS" \
            --template-body "file://$TEMPLATE_DIR/02-efs-storage.yaml" \
            --parameters "file://$TEMP_PARAMS_FILE" \
            --region "$REGION" \
            --capabilities CAPABILITY_IAM \
            2>/dev/null || {
                if [[ $? -eq 254 ]]; then
                    print_info "No updates to be performed on $STACK_NAME_EFS"
                    OPERATION=""
                else
                    print_error "Failed to update stack $STACK_NAME_EFS"
                    exit 1
                fi
            }
    fi
else
    print_info "Creating stack $STACK_NAME_EFS..."
    OPERATION="create"

    aws cloudformation create-stack \
        --stack-name "$STACK_NAME_EFS" \
        --template-body "file://$TEMPLATE_DIR/02-efs-storage.yaml" \
        --parameters "file://$TEMP_PARAMS_FILE" \
        --region "$REGION" \
        --capabilities CAPABILITY_IAM
fi

# Wait for EFS stack to complete
if [[ "$OPERATION" != "" ]]; then
    if ! wait_for_stack "$STACK_NAME_EFS" "$OPERATION"; then
        print_error "EFS stack deployment failed. Check AWS Console for details."
        exit 1
    fi
fi

# Display EFS outputs
get_stack_outputs "$STACK_NAME_EFS"

# ========================================
# Step 3: Deploy Application Load Balancer
# ========================================
STACK_NAME_ALB="${PROJECT_NAME}-alb-${ENVIRONMENT}"

print_header "Step 3: Deploying Application Load Balancer"

print_info "Using parameters from $TEMPLATE_DIR/common-parameters.json"

# Detect public IP for security group
print_info "Detecting your public IP address for security..."
MY_PUBLIC_IP=$(get_public_ip)
print_success "Detected IP: ${MY_PUBLIC_IP}/32"
print_info "ALB will only accept traffic from this IP address"

# Create parameters file with ALB-specific parameters
TEMP_ALB_PARAMS_FILE_BASE=$(create_params_file "VpcId" "SubnetIds" "CertificateArn" "ECSSecurityGroupId")

# Add AllowedCidr with detected IP (insert before closing bracket)
TEMP_ALB_PARAMS_FILE=$(mktemp)
sed '$d' "$TEMP_ALB_PARAMS_FILE_BASE" > "$TEMP_ALB_PARAMS_FILE"
cat >> "$TEMP_ALB_PARAMS_FILE" <<EOF
  ,
  {
    "ParameterKey": "AllowedCidr",
    "ParameterValue": "${MY_PUBLIC_IP}/32"
  }
]
EOF
rm -f "$TEMP_ALB_PARAMS_FILE_BASE"

OPERATION=""

if check_stack_exists "$STACK_NAME_ALB"; then
    CURRENT_STATUS=$(get_stack_status "$STACK_NAME_ALB")
    print_info "Stack $STACK_NAME_ALB exists with status: $CURRENT_STATUS"

    if is_stack_complete "$STACK_NAME_ALB"; then
        print_success "Stack $STACK_NAME_ALB is already in a completed state. Skipping deployment."
    else
        print_info "Stack $STACK_NAME_ALB needs updating..."
        OPERATION="update"

        aws cloudformation update-stack \
            --stack-name "$STACK_NAME_ALB" \
            --template-body "file://$TEMPLATE_DIR/03-load-balancer.yaml" \
            --parameters "file://$TEMP_ALB_PARAMS_FILE" \
            --region "$REGION" \
            --capabilities CAPABILITY_IAM \
            2>/dev/null || {
                if [[ $? -eq 254 ]]; then
                    print_info "No updates to be performed on $STACK_NAME_ALB"
                    OPERATION=""
                else
                    print_error "Failed to update stack $STACK_NAME_ALB"
                    exit 1
                fi
            }
    fi
else
    print_info "Creating stack $STACK_NAME_ALB..."
    OPERATION="create"

    aws cloudformation create-stack \
        --stack-name "$STACK_NAME_ALB" \
        --template-body "file://$TEMPLATE_DIR/03-load-balancer.yaml" \
        --parameters "file://$TEMP_ALB_PARAMS_FILE" \
        --region "$REGION" \
        --capabilities CAPABILITY_IAM
fi

# Wait for ALB stack to complete
if [[ "$OPERATION" != "" ]]; then
    if ! wait_for_stack "$STACK_NAME_ALB" "$OPERATION"; then
        print_error "ALB stack deployment failed. Check AWS Console for details."
        exit 1
    fi
fi

# Display ALB outputs
get_stack_outputs "$STACK_NAME_ALB"

# ========================================
# Step 4: Deploy IAM Roles
# ========================================
STACK_NAME_IAM="${PROJECT_NAME}-iam-${ENVIRONMENT}"

print_header "Step 4: Deploying IAM Roles"

OPERATION=""

if check_stack_exists "$STACK_NAME_IAM"; then
    CURRENT_STATUS=$(get_stack_status "$STACK_NAME_IAM")
    print_info "Stack $STACK_NAME_IAM exists with status: $CURRENT_STATUS"

    if is_stack_complete "$STACK_NAME_IAM"; then
        print_success "Stack $STACK_NAME_IAM is already in a completed state. Skipping deployment."
    else
        print_info "Stack $STACK_NAME_IAM needs updating..."
        OPERATION="update"

        aws cloudformation update-stack \
            --stack-name "$STACK_NAME_IAM" \
            --template-body "file://$TEMPLATE_DIR/04-iam-roles.yaml" \
            --parameters \
                ParameterKey=ProjectName,ParameterValue="$PROJECT_NAME" \
                ParameterKey=Environment,ParameterValue="$ENVIRONMENT" \
            --region "$REGION" \
            --capabilities CAPABILITY_NAMED_IAM \
            2>/dev/null || {
                if [[ $? -eq 254 ]]; then
                    print_info "No updates to be performed on $STACK_NAME_IAM"
                    OPERATION=""
                else
                    print_error "Failed to update stack $STACK_NAME_IAM"
                    exit 1
                fi
            }
    fi
else
    print_info "Creating stack $STACK_NAME_IAM..."
    OPERATION="create"

    aws cloudformation create-stack \
        --stack-name "$STACK_NAME_IAM" \
        --template-body "file://$TEMPLATE_DIR/04-iam-roles.yaml" \
        --parameters \
            ParameterKey=ProjectName,ParameterValue="$PROJECT_NAME" \
            ParameterKey=Environment,ParameterValue="$ENVIRONMENT" \
        --region "$REGION" \
        --capabilities CAPABILITY_NAMED_IAM
fi

# Wait for IAM stack to complete
if [[ "$OPERATION" != "" ]]; then
    if ! wait_for_stack "$STACK_NAME_IAM" "$OPERATION"; then
        print_error "IAM stack deployment failed. Check AWS Console for details."
        exit 1
    fi
fi

# Display IAM outputs
get_stack_outputs "$STACK_NAME_IAM"

# ========================================
# Step 5: Deploy ECS Cluster
# ========================================
STACK_NAME_CLUSTER="${PROJECT_NAME}-cluster-${ENVIRONMENT}"

print_header "Step 5: Deploying ECS Cluster"

OPERATION=""

if check_stack_exists "$STACK_NAME_CLUSTER"; then
    CURRENT_STATUS=$(get_stack_status "$STACK_NAME_CLUSTER")
    print_info "Stack $STACK_NAME_CLUSTER exists with status: $CURRENT_STATUS"

    if is_stack_complete "$STACK_NAME_CLUSTER"; then
        print_success "Stack $STACK_NAME_CLUSTER is already in a completed state. Skipping deployment."
    else
        print_info "Stack $STACK_NAME_CLUSTER needs updating..."
        OPERATION="update"

        aws cloudformation update-stack \
            --stack-name "$STACK_NAME_CLUSTER" \
            --template-body "file://$TEMPLATE_DIR/05-ecs-cluster.yaml" \
            --parameters \
                ParameterKey=ProjectName,ParameterValue="$PROJECT_NAME" \
                ParameterKey=Environment,ParameterValue="$ENVIRONMENT" \
            --region "$REGION" \
            --capabilities CAPABILITY_IAM \
            2>/dev/null || {
                if [[ $? -eq 254 ]]; then
                    print_info "No updates to be performed on $STACK_NAME_CLUSTER"
                    OPERATION=""
                else
                    print_error "Failed to update stack $STACK_NAME_CLUSTER"
                    exit 1
                fi
            }
    fi
else
    print_info "Creating stack $STACK_NAME_CLUSTER..."
    OPERATION="create"

    aws cloudformation create-stack \
        --stack-name "$STACK_NAME_CLUSTER" \
        --template-body "file://$TEMPLATE_DIR/05-ecs-cluster.yaml" \
        --parameters \
            ParameterKey=ProjectName,ParameterValue="$PROJECT_NAME" \
            ParameterKey=Environment,ParameterValue="$ENVIRONMENT" \
        --region "$REGION" \
        --capabilities CAPABILITY_IAM
fi

# Wait for Cluster stack to complete
if [[ "$OPERATION" != "" ]]; then
    if ! wait_for_stack "$STACK_NAME_CLUSTER" "$OPERATION"; then
        print_error "Cluster stack deployment failed. Check AWS Console for details."
        exit 1
    fi
fi

# Display Cluster outputs
get_stack_outputs "$STACK_NAME_CLUSTER"

# ========================================
# Step 6: Deploy ECS Service
# ========================================
STACK_NAME_SERVICE="${PROJECT_NAME}-service-${ENVIRONMENT}"

print_header "Step 6: Deploying ECS Service"

print_info "Using parameters from $TEMPLATE_DIR/common-parameters.json"

# Create parameters file with ECS Service-specific parameters
TEMP_ECS_PARAMS_FILE=$(create_params_file "SubnetIds" "ECSSecurityGroupId" "FrontendImageTag" "BackendImageTag" "TaskCpu" "TaskMemory" "DesiredCount")

OPERATION=""

if check_stack_exists "$STACK_NAME_SERVICE"; then
    CURRENT_STATUS=$(get_stack_status "$STACK_NAME_SERVICE")
    print_info "Stack $STACK_NAME_SERVICE exists with status: $CURRENT_STATUS"

    if is_stack_complete "$STACK_NAME_SERVICE"; then
        print_success "Stack $STACK_NAME_SERVICE is already in a completed state. Skipping deployment."
    else
        print_info "Stack $STACK_NAME_SERVICE needs updating..."
        OPERATION="update"

        aws cloudformation update-stack \
            --stack-name "$STACK_NAME_SERVICE" \
            --template-body "file://$TEMPLATE_DIR/06-ecs-service.yaml" \
            --parameters "file://$TEMP_ECS_PARAMS_FILE" \
            --region "$REGION" \
            --capabilities CAPABILITY_IAM \
            2>/dev/null || {
                if [[ $? -eq 254 ]]; then
                    print_info "No updates to be performed on $STACK_NAME_SERVICE"
                    OPERATION=""
                else
                    print_error "Failed to update stack $STACK_NAME_SERVICE"
                    exit 1
                fi
            }
    fi
else
    print_info "Creating stack $STACK_NAME_SERVICE..."
    OPERATION="create"

    aws cloudformation create-stack \
        --stack-name "$STACK_NAME_SERVICE" \
        --template-body "file://$TEMPLATE_DIR/06-ecs-service.yaml" \
        --parameters "file://$TEMP_ECS_PARAMS_FILE" \
        --region "$REGION" \
        --capabilities CAPABILITY_IAM
fi

# Wait for Service stack to complete
if [[ "$OPERATION" != "" ]]; then
    if ! wait_for_stack "$STACK_NAME_SERVICE" "$OPERATION"; then
        print_error "Service stack deployment failed. Check AWS Console for details."
        exit 1
    fi
fi

# Display Service outputs
get_stack_outputs "$STACK_NAME_SERVICE"

# ========================================
# Step 7: Deploy Cognito User Pool (Optional)
# ========================================
if [[ "$USE_EXISTING_COGNITO" == true ]]; then
    print_header "Step 7: Using Existing Cognito User Pool"
    print_success "Reusing existing Cognito User Pool (skipping stack creation)"
    print_success "  Pool ARN: $EXISTING_COGNITO_ARN"
    print_success "  Client ID: $EXISTING_COGNITO_CLIENT_ID"
    print_success "  Domain: $EXISTING_COGNITO_DOMAIN"
elif [[ "$ENABLE_COGNITO" == true ]]; then
    STACK_NAME_COGNITO="${PROJECT_NAME}-cognito-${ENVIRONMENT}"

    print_header "Step 7: Deploying Cognito User Pool"

    TEMP_COGNITO_PARAMS_FILE=$(create_params_file "AppDomainName" "CognitoDomainPrefix")

    OPERATION=""

    if check_stack_exists "$STACK_NAME_COGNITO"; then
        CURRENT_STATUS=$(get_stack_status "$STACK_NAME_COGNITO")
        print_info "Stack $STACK_NAME_COGNITO exists with status: $CURRENT_STATUS"

        if is_stack_complete "$STACK_NAME_COGNITO"; then
            print_success "Stack $STACK_NAME_COGNITO is already in a completed state. Skipping deployment."
        else
            print_info "Stack $STACK_NAME_COGNITO needs updating..."
            OPERATION="update"

            aws cloudformation update-stack \
                --stack-name "$STACK_NAME_COGNITO" \
                --template-body "file://$TEMPLATE_DIR/08-cognito.yaml" \
                --parameters "file://$TEMP_COGNITO_PARAMS_FILE" \
                --region "$REGION" \
                --capabilities CAPABILITY_IAM \
                2>/dev/null || {
                    if [[ $? -eq 254 ]]; then
                        print_info "No updates to be performed on $STACK_NAME_COGNITO"
                        OPERATION=""
                    else
                        print_error "Failed to update stack $STACK_NAME_COGNITO"
                        exit 1
                    fi
                }
        fi
    else
        print_info "Creating stack $STACK_NAME_COGNITO..."
        OPERATION="create"

        aws cloudformation create-stack \
            --stack-name "$STACK_NAME_COGNITO" \
            --template-body "file://$TEMPLATE_DIR/08-cognito.yaml" \
            --parameters "file://$TEMP_COGNITO_PARAMS_FILE" \
            --region "$REGION" \
            --capabilities CAPABILITY_IAM
    fi

    if [[ "$OPERATION" != "" ]]; then
        if ! wait_for_stack "$STACK_NAME_COGNITO" "$OPERATION"; then
            print_error "Cognito stack deployment failed. Check AWS Console for details."
            exit 1
        fi
    fi

    get_stack_outputs "$STACK_NAME_COGNITO"
else
    print_info "Skipping Step 7: Cognito not configured (CognitoDomainPrefix or AppDomainName is empty)"
fi

# ========================================
# Step 8: Update ALB with Cognito/CloudFront Settings (Optional)
# ========================================
if [[ "$ENABLE_COGNITO" == true ]] || [[ "$ENABLE_CLOUDFRONT" == true ]]; then
    print_header "Step 8: Updating ALB with Cognito/WAF Configuration"

    # Generate or retrieve origin verify secret for WAF
    ORIGIN_VERIFY_SECRET=""
    if [[ "$ENABLE_CLOUDFRONT" == true ]]; then
        SSM_PARAM_NAME="/${PROJECT_NAME}/${ENVIRONMENT}/origin-verify-secret"

        # Try to retrieve existing secret from SSM
        ORIGIN_VERIFY_SECRET=$(aws ssm get-parameter \
            --name "$SSM_PARAM_NAME" \
            --with-decryption \
            --query "Parameter.Value" \
            --output text \
            --region "$REGION" 2>/dev/null) || true

        if [[ -z "$ORIGIN_VERIFY_SECRET" || "$ORIGIN_VERIFY_SECRET" == "None" ]]; then
            # Generate new secret
            ORIGIN_VERIFY_SECRET=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
            aws ssm put-parameter \
                --name "$SSM_PARAM_NAME" \
                --value "$ORIGIN_VERIFY_SECRET" \
                --type SecureString \
                --description "Origin verify header secret for CloudFront to ALB WAF validation" \
                --region "$REGION"
            print_success "Generated and stored origin verify secret in SSM: $SSM_PARAM_NAME"
        else
            print_success "Retrieved origin verify secret from SSM: $SSM_PARAM_NAME"
        fi
    fi

    # Retrieve Cognito configuration
    COGNITO_USER_POOL_ARN=""
    COGNITO_CLIENT_ID=""
    COGNITO_DOMAIN=""

    if [[ "$USE_EXISTING_COGNITO" == true ]]; then
        # Use pre-existing Cognito pool values from common-parameters.json
        COGNITO_USER_POOL_ARN="$EXISTING_COGNITO_ARN"
        COGNITO_CLIENT_ID="$EXISTING_COGNITO_CLIENT_ID"
        COGNITO_DOMAIN="$EXISTING_COGNITO_DOMAIN"

        print_success "Using existing Cognito User Pool ARN: $COGNITO_USER_POOL_ARN"
        print_success "Using existing Cognito Client ID: $COGNITO_CLIENT_ID"
        print_success "Using existing Cognito Domain: $COGNITO_DOMAIN"
    elif [[ "$ENABLE_COGNITO" == true ]]; then
        # Retrieve values from Cognito CloudFormation stack outputs
        STACK_NAME_COGNITO="${PROJECT_NAME}-cognito-${ENVIRONMENT}"

        COGNITO_USER_POOL_ARN=$(aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME_COGNITO" \
            --region "$REGION" \
            --query "Stacks[0].Outputs[?OutputKey=='UserPoolArn'].OutputValue" \
            --output text)

        COGNITO_CLIENT_ID=$(aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME_COGNITO" \
            --region "$REGION" \
            --query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" \
            --output text)

        COGNITO_DOMAIN=$(aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME_COGNITO" \
            --region "$REGION" \
            --query "Stacks[0].Outputs[?OutputKey=='UserPoolDomainName'].OutputValue" \
            --output text)

        print_success "Cognito User Pool ARN: $COGNITO_USER_POOL_ARN"
        print_success "Cognito Client ID: $COGNITO_CLIENT_ID"
        print_success "Cognito Domain: $COGNITO_DOMAIN"
    fi

    # ALB AllowedCidr is always the deployer's IP (never 0.0.0.0/0)
    ALB_ALLOWED_CIDR="${MY_PUBLIC_IP}/32"

    # Look up CloudFront managed prefix list for SG ingress
    CF_PREFIX_LIST_ID=""
    if [[ "$ENABLE_CLOUDFRONT" == true ]]; then
        CF_PREFIX_LIST_ID=$(aws ec2 describe-managed-prefix-lists \
            --filters "Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing" \
            --region "$REGION" \
            --query 'PrefixLists[0].PrefixListId' \
            --output text)
        if [[ -z "$CF_PREFIX_LIST_ID" || "$CF_PREFIX_LIST_ID" == "None" ]]; then
            print_error "Could not find CloudFront managed prefix list"
            exit 1
        fi
        print_success "CloudFront prefix list ID: $CF_PREFIX_LIST_ID"
    fi

    # Build ALB params file with Cognito/WAF additions
    TEMP_ALB_UPDATE_BASE=$(create_params_file "VpcId" "SubnetIds" "CertificateArn" "ECSSecurityGroupId")

    TEMP_ALB_UPDATE_PARAMS_FILE=$(mktemp)
    sed '$d' "$TEMP_ALB_UPDATE_BASE" > "$TEMP_ALB_UPDATE_PARAMS_FILE"
    cat >> "$TEMP_ALB_UPDATE_PARAMS_FILE" <<EOF
  ,
  {
    "ParameterKey": "AllowedCidr",
    "ParameterValue": "${ALB_ALLOWED_CIDR}"
  },
  {
    "ParameterKey": "CognitoUserPoolArn",
    "ParameterValue": "${COGNITO_USER_POOL_ARN}"
  },
  {
    "ParameterKey": "CognitoUserPoolClientId",
    "ParameterValue": "${COGNITO_CLIENT_ID}"
  },
  {
    "ParameterKey": "CognitoUserPoolDomain",
    "ParameterValue": "${COGNITO_DOMAIN}"
  },
  {
    "ParameterKey": "OriginVerifyHeaderValue",
    "ParameterValue": "${ORIGIN_VERIFY_SECRET}"
  },
  {
    "ParameterKey": "CloudFrontPrefixListId",
    "ParameterValue": "${CF_PREFIX_LIST_ID}"
  }
]
EOF
    rm -f "$TEMP_ALB_UPDATE_BASE"

    # Force update ALB stack (even if complete)
    print_info "Updating stack $STACK_NAME_ALB with Cognito/WAF parameters..."

    aws cloudformation update-stack \
        --stack-name "$STACK_NAME_ALB" \
        --template-body "file://$TEMPLATE_DIR/03-load-balancer.yaml" \
        --parameters "file://$TEMP_ALB_UPDATE_PARAMS_FILE" \
        --region "$REGION" \
        --capabilities CAPABILITY_IAM \
        2>/dev/null || {
            RESULT=$?
            if [[ $RESULT -eq 254 ]] || [[ $RESULT -eq 0 ]]; then
                print_info "No updates to be performed on $STACK_NAME_ALB"
            else
                print_error "Failed to update stack $STACK_NAME_ALB"
                exit 1
            fi
        }

    # Wait for update if it started
    CURRENT_STATUS=$(get_stack_status "$STACK_NAME_ALB")
    if [[ "$CURRENT_STATUS" == "UPDATE_IN_PROGRESS" ]]; then
        if ! wait_for_stack "$STACK_NAME_ALB" "update"; then
            print_error "ALB stack update failed. Check AWS Console for details."
            exit 1
        fi
    fi

    get_stack_outputs "$STACK_NAME_ALB"
    rm -f "$TEMP_ALB_UPDATE_PARAMS_FILE"
else
    print_info "Skipping Step 8: No Cognito/WAF configuration to apply to ALB"
fi

# ========================================
# Step 9: Deploy CloudFront Distribution (Optional)
# ========================================
if [[ "$ENABLE_CLOUDFRONT" == true ]]; then
    STACK_NAME_CF="${PROJECT_NAME}-cloudfront-${ENVIRONMENT}"

    print_header "Step 9: Deploying CloudFront Distribution"

    # Build params with OriginVerifyHeaderValue
    TEMP_CF_PARAMS_BASE=$(create_params_file "AppDomainName" "HostedZoneId" "CloudFrontCertificateArn")
    TEMP_CF_PARAMS_FILE=$(mktemp)
    sed '$d' "$TEMP_CF_PARAMS_BASE" > "$TEMP_CF_PARAMS_FILE"
    cat >> "$TEMP_CF_PARAMS_FILE" <<EOF
  ,
  {
    "ParameterKey": "OriginVerifyHeaderValue",
    "ParameterValue": "${ORIGIN_VERIFY_SECRET}"
  }
]
EOF
    rm -f "$TEMP_CF_PARAMS_BASE"

    OPERATION=""

    if check_stack_exists "$STACK_NAME_CF"; then
        CURRENT_STATUS=$(get_stack_status "$STACK_NAME_CF")
        print_info "Stack $STACK_NAME_CF exists with status: $CURRENT_STATUS"

        if is_stack_complete "$STACK_NAME_CF"; then
            print_success "Stack $STACK_NAME_CF is already in a completed state. Skipping deployment."
        else
            print_info "Stack $STACK_NAME_CF needs updating..."
            OPERATION="update"

            aws cloudformation update-stack \
                --stack-name "$STACK_NAME_CF" \
                --template-body "file://$TEMPLATE_DIR/09-cloudfront.yaml" \
                --parameters "file://$TEMP_CF_PARAMS_FILE" \
                --region "$REGION" \
                --capabilities CAPABILITY_IAM \
                2>/dev/null || {
                    if [[ $? -eq 254 ]]; then
                        print_info "No updates to be performed on $STACK_NAME_CF"
                        OPERATION=""
                    else
                        print_error "Failed to update stack $STACK_NAME_CF"
                        exit 1
                    fi
                }
        fi
    else
        print_info "Creating stack $STACK_NAME_CF..."
        print_info "Note: CloudFront distributions can take 10-15 minutes to deploy..."
        OPERATION="create"

        aws cloudformation create-stack \
            --stack-name "$STACK_NAME_CF" \
            --template-body "file://$TEMPLATE_DIR/09-cloudfront.yaml" \
            --parameters "file://$TEMP_CF_PARAMS_FILE" \
            --region "$REGION" \
            --capabilities CAPABILITY_IAM
    fi

    if [[ "$OPERATION" != "" ]]; then
        if ! wait_for_stack "$STACK_NAME_CF" "$OPERATION"; then
            print_error "CloudFront stack deployment failed. Check AWS Console for details."
            exit 1
        fi
    fi

    get_stack_outputs "$STACK_NAME_CF"
else
    print_info "Skipping Step 9: CloudFront not configured (AppDomainName, HostedZoneId, or CloudFrontCertificateArn is empty)"
fi

# ========================================
# Deployment Complete
# ========================================
print_header "Deployment Complete!"

echo ""
print_success "All CloudFormation stacks deployed successfully!"
echo ""
echo "Stack Names:"
echo "  1. ECR: $STACK_NAME_ECR"
echo "  2. EFS: $STACK_NAME_EFS"
echo "  3. ALB: $STACK_NAME_ALB"
echo "  4. IAM: $STACK_NAME_IAM"
echo "  5. Cluster: $STACK_NAME_CLUSTER"
echo "  6. Service: $STACK_NAME_SERVICE"
if [[ "$USE_EXISTING_COGNITO" == true ]]; then
    echo "  7. Cognito: (existing pool - no stack)"
elif [[ "$ENABLE_COGNITO" == true ]]; then
    echo "  7. Cognito: ${PROJECT_NAME}-cognito-${ENVIRONMENT}"
fi
if [[ "$ENABLE_COGNITO" == true ]] || [[ "$ENABLE_CLOUDFRONT" == true ]]; then
    echo "  8. ALB Updated: $STACK_NAME_ALB (Cognito/WAF)"
fi
if [[ "$ENABLE_CLOUDFRONT" == true ]]; then
    echo "  9. CloudFront: ${PROJECT_NAME}-cloudfront-${ENVIRONMENT}"
fi
echo ""
if [[ "$ENABLE_CLOUDFRONT" == true ]]; then
    echo "Application URL:"
    echo "  https://$APP_DOMAIN_NAME"
else
    echo "Application URL:"
    echo "  Check the ALB DNS output above for the application URL"
fi
echo ""
echo "Next Steps:"
echo "  1. Verify all services are running: aws ecs describe-services --cluster ${PROJECT_NAME}-cluster-${ENVIRONMENT} --services ${PROJECT_NAME}-service-${ENVIRONMENT} --region $REGION"
echo "  2. Check application health at the URL above"
if [[ "$ENABLE_COGNITO" == true ]]; then
    if [[ "$USE_EXISTING_COGNITO" == true ]]; then
        # Extract pool ID from ARN (last segment after '/')
        COGNITO_POOL_ID=$(echo "$EXISTING_COGNITO_ARN" | awk -F'/' '{print $NF}')
    else
        COGNITO_POOL_ID=$(aws cloudformation describe-stacks \
            --stack-name "${PROJECT_NAME}-cognito-${ENVIRONMENT}" \
            --region "$REGION" \
            --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
            --output text 2>/dev/null || echo "<pool-id>")
    fi
    echo "  3. Create Cognito users: aws cognito-idp admin-create-user --user-pool-id $COGNITO_POOL_ID --username <email> --user-attributes Name=email,Value=<email> --region $REGION"
fi
echo ""
