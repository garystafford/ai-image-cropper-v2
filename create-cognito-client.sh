#!/bin/bash

# AI Image Cropper v2 - Create Cognito App Client
# Creates an ALB-compatible App Client in an existing Cognito User Pool
# and updates common-parameters.json with the new Client ID.
#
# Prerequisites:
#   - AWS CLI installed and configured
#   - Existing Cognito User Pool
#   - common-parameters.json with CognitoUserPoolArn and AppDomainName set
#
# Usage:
#   ./create-cognito-client.sh
#   ./create-cognito-client.sh --pool-id us-east-1_XXXXXXXXX  # override pool ID

set -eo pipefail  # Exit on error, fail on pipe errors

# ========================================
# Configuration
# ========================================
PROJECT_NAME="ai-image-cropper-v2"
REGION="us-east-1"
TEMPLATE_DIR="cloudformation"
PARAMS_FILE="$TEMPLATE_DIR/common-parameters.json"

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

get_param_value() {
    local key=$1
    grep -A 1 "\"ParameterKey\": \"$key\"" "$PARAMS_FILE" \
        | grep "ParameterValue" \
        | sed 's/.*"ParameterValue": "\(.*\)".*/\1/'
}

# ========================================
# Validation
# ========================================
if [[ ! -f "$PARAMS_FILE" ]]; then
    print_error "Parameters file not found: $PARAMS_FILE"
    print_info "Run from the project root directory."
    exit 1
fi

# ========================================
# Resolve User Pool ID
# ========================================
print_header "Create Cognito App Client for ALB"

# Accept pool ID from CLI argument or extract from ARN in parameters
POOL_ID=""
if [[ "$1" == "--pool-id" && -n "$2" ]]; then
    POOL_ID="$2"
    print_info "Using pool ID from argument: $POOL_ID"
else
    COGNITO_ARN=$(get_param_value "CognitoUserPoolArn")
    if [[ -z "$COGNITO_ARN" ]]; then
        print_error "CognitoUserPoolArn is not set in $PARAMS_FILE"
        print_info "Set it first, or pass --pool-id <id> as an argument."
        exit 1
    fi
    # Extract pool ID from ARN (last segment after '/')
    POOL_ID=$(echo "$COGNITO_ARN" | awk -F'/' '{print $NF}')
    print_info "Extracted pool ID from CognitoUserPoolArn: $POOL_ID"
fi

APP_DOMAIN=$(get_param_value "AppDomainName")
if [[ -z "$APP_DOMAIN" ]]; then
    print_error "AppDomainName is not set in $PARAMS_FILE"
    exit 1
fi

CALLBACK_URL="https://${APP_DOMAIN}/oauth2/idpresponse"
CLIENT_NAME="${PROJECT_NAME}-alb-client"

print_info "User Pool ID: $POOL_ID"
print_info "Callback URL: $CALLBACK_URL"
print_info "Client Name:  $CLIENT_NAME"
echo ""

# ========================================
# Check for existing client
# ========================================
print_info "Checking for existing app client '$CLIENT_NAME'..."

EXISTING_CLIENT_ID=$(aws cognito-idp list-user-pool-clients \
    --user-pool-id "$POOL_ID" \
    --region "$REGION" \
    --query "UserPoolClients[?ClientName=='${CLIENT_NAME}'].ClientId" \
    --output text 2>/dev/null) || true

if [[ -n "$EXISTING_CLIENT_ID" && "$EXISTING_CLIENT_ID" != "None" ]]; then
    print_info "App client '$CLIENT_NAME' already exists: $EXISTING_CLIENT_ID"
    echo ""
    read -rp "Use existing client? (y/N): " USE_EXISTING
    if [[ "$USE_EXISTING" =~ ^[Yy]$ ]]; then
        CLIENT_ID="$EXISTING_CLIENT_ID"
        print_success "Using existing client: $CLIENT_ID"
    else
        print_info "Creating a new client..."
        EXISTING_CLIENT_ID=""
    fi
fi

# ========================================
# Create App Client
# ========================================
if [[ -z "$EXISTING_CLIENT_ID" || "$EXISTING_CLIENT_ID" == "None" ]]; then
    print_info "Creating Cognito App Client..."

    CLIENT_OUTPUT=$(aws cognito-idp create-user-pool-client \
        --user-pool-id "$POOL_ID" \
        --client-name "$CLIENT_NAME" \
        --generate-secret \
        --allowed-o-auth-flows code \
        --allowed-o-auth-flows-user-pool-client \
        --allowed-o-auth-scopes openid \
        --callback-urls "$CALLBACK_URL" \
        --supported-identity-providers COGNITO \
        --region "$REGION" \
        --output json)

    CLIENT_ID=$(echo "$CLIENT_OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['UserPoolClient']['ClientId'])")

    print_success "Created App Client: $CLIENT_ID"
fi

# ========================================
# Resolve Cognito Domain
# ========================================
COGNITO_DOMAIN=$(get_param_value "CognitoUserPoolDomain")
if [[ -z "$COGNITO_DOMAIN" ]]; then
    # Look up the domain from the user pool
    DOMAIN_PREFIX=$(aws cognito-idp describe-user-pool \
        --user-pool-id "$POOL_ID" \
        --region "$REGION" \
        --query "UserPool.Domain" \
        --output text 2>/dev/null) || true

    if [[ -n "$DOMAIN_PREFIX" && "$DOMAIN_PREFIX" != "None" ]]; then
        COGNITO_DOMAIN="${DOMAIN_PREFIX}.auth.${REGION}.amazoncognito.com"
        print_success "Resolved Cognito domain: $COGNITO_DOMAIN"
    else
        print_error "Could not determine Cognito hosted UI domain."
        print_info "Set CognitoUserPoolDomain manually in $PARAMS_FILE"
    fi
fi

# ========================================
# Update common-parameters.json
# ========================================
echo ""
print_info "Updating $PARAMS_FILE..."

# Update CognitoUserPoolClientId
if grep -q '"CognitoUserPoolClientId"' "$PARAMS_FILE"; then
    # Replace existing value
    sed -i.bak "$(grep -n '"CognitoUserPoolClientId"' "$PARAMS_FILE" | head -1 | cut -d: -f1),+3 s/\"ParameterValue\": \"[^\"]*\"/\"ParameterValue\": \"$CLIENT_ID\"/" "$PARAMS_FILE"
    rm -f "${PARAMS_FILE}.bak"
    print_success "Updated CognitoUserPoolClientId: $CLIENT_ID"
else
    print_info "CognitoUserPoolClientId not found in $PARAMS_FILE — add it manually"
fi

# Update CognitoUserPoolDomain if we resolved it
if [[ -n "$COGNITO_DOMAIN" ]] && grep -q '"CognitoUserPoolDomain"' "$PARAMS_FILE"; then
    CURRENT_DOMAIN=$(get_param_value "CognitoUserPoolDomain")
    if [[ -z "$CURRENT_DOMAIN" || "$CURRENT_DOMAIN" == "None" ]]; then
        sed -i.bak "$(grep -n '"CognitoUserPoolDomain"' "$PARAMS_FILE" | head -1 | cut -d: -f1),+3 s|\"ParameterValue\": \"[^\"]*\"|\"ParameterValue\": \"$COGNITO_DOMAIN\"|" "$PARAMS_FILE"
        rm -f "${PARAMS_FILE}.bak"
        print_success "Updated CognitoUserPoolDomain: $COGNITO_DOMAIN"
    fi
fi

# ========================================
# Summary
# ========================================
echo ""
print_header "Done"
echo ""
echo "Cognito App Client created for ALB integration:"
echo "  Pool ID:    $POOL_ID"
echo "  Client ID:  $CLIENT_ID"
echo "  Callback:   $CALLBACK_URL"
if [[ -n "$COGNITO_DOMAIN" ]]; then
    echo "  Domain:     $COGNITO_DOMAIN"
fi
echo ""
echo "Next steps:"
echo "  1. Verify $PARAMS_FILE has the correct CognitoUserPoolClientId"
echo "  2. Run ./deploy-cloudformation.sh to deploy CloudFront + WAF + Cognito auth"
echo ""
