#!/bin/bash
set -euo pipefail
# Creates CodeBuild project that builds the Heliox Docker image and pushes to ECR.
# Run this once. Subsequent builds trigger automatically via GitHub Actions.

ACCOUNT_ID="038462779905"
REGION="us-east-1"
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
ECR_REPOSITORY="heliox"
PROJECT_NAME="heliox-build"
GITHUB_REPO="https://github.com/Sarishc/Heliox-AI"

echo "=== Step 0: Creating CodeBuild project ==="
echo "Account: $ACCOUNT_ID | Region: $REGION"

# ── IAM role for CodeBuild ────────────────────────────────────────────────────
ROLE_NAME="heliox-codebuild-role"

if aws iam get-role --role-name "$ROLE_NAME" &>/dev/null; then
  echo "IAM role $ROLE_NAME already exists — skipping"
else
  echo "Creating IAM role $ROLE_NAME..."
  aws iam create-role \
    --role-name "$ROLE_NAME" \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "codebuild.amazonaws.com"},
        "Action": "sts:AssumeRole"
      }]
    }' > /dev/null

  # ECR push permissions
  aws iam put-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-name "heliox-codebuild-policy" \
    --policy-document "{
      \"Version\": \"2012-10-17\",
      \"Statement\": [
        {
          \"Effect\": \"Allow\",
          \"Action\": [
            \"ecr:GetAuthorizationToken\",
            \"ecr:BatchCheckLayerAvailability\",
            \"ecr:GetDownloadUrlForLayer\",
            \"ecr:BatchGetImage\",
            \"ecr:PutImage\",
            \"ecr:InitiateLayerUpload\",
            \"ecr:UploadLayerPart\",
            \"ecr:CompleteLayerUpload\"
          ],
          \"Resource\": \"*\"
        },
        {
          \"Effect\": \"Allow\",
          \"Action\": [
            \"logs:CreateLogGroup\",
            \"logs:CreateLogStream\",
            \"logs:PutLogEvents\"
          ],
          \"Resource\": \"arn:aws:logs:${REGION}:${ACCOUNT_ID}:log-group:/aws/codebuild/${PROJECT_NAME}:*\"
        }
      ]
    }"

  echo "Waiting for IAM role to propagate..."
  sleep 10
fi

ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

# ── Connect CodeBuild to GitHub (requires OAuth or PAT) ───────────────────────
echo ""
echo "NOTE: CodeBuild needs GitHub credentials to clone your repo."
echo "If you haven't connected GitHub yet, run:"
echo ""
echo "  aws codebuild import-source-credentials \\"
echo "    --server-type GITHUB \\"
echo "    --auth-type PERSONAL_ACCESS_TOKEN \\"
echo "    --token YOUR_GITHUB_PAT \\"
echo "    --region $REGION"
echo ""
echo "Alternatively, connect via the AWS Console → CodeBuild → Source credentials."
echo "Press Enter to continue (assuming credentials are already set)..."
read -r

# ── Create CodeBuild project ──────────────────────────────────────────────────
if aws codebuild batch-get-projects --names "$PROJECT_NAME" --region "$REGION" \
    --query 'projects[0].name' --output text 2>/dev/null | grep -q "$PROJECT_NAME"; then
  echo "CodeBuild project $PROJECT_NAME already exists — skipping"
else
  echo "Creating CodeBuild project $PROJECT_NAME..."
  aws codebuild create-project \
    --region "$REGION" \
    --name "$PROJECT_NAME" \
    --description "Builds Heliox Docker image and pushes to ECR" \
    --source "{
      \"type\": \"GITHUB\",
      \"location\": \"${GITHUB_REPO}\",
      \"buildspec\": \"aws/codebuild/buildspec.yml\",
      \"gitCloneDepth\": 1
    }" \
    --artifacts '{"type": "NO_ARTIFACTS"}' \
    --environment "{
      \"type\": \"LINUX_CONTAINER\",
      \"image\": \"aws/codebuild/standard:7.0\",
      \"computeType\": \"BUILD_GENERAL1_SMALL\",
      \"privilegedMode\": true,
      \"environmentVariables\": [
        {\"name\": \"ECR_REGISTRY\", \"value\": \"${ECR_REGISTRY}\"},
        {\"name\": \"ECR_REPOSITORY\", \"value\": \"${ECR_REPOSITORY}\"},
        {\"name\": \"AWS_DEFAULT_REGION\", \"value\": \"${REGION}\"}
      ]
    }" \
    --service-role "$ROLE_ARN" \
    --logs-config "{
      \"cloudWatchLogs\": {
        \"status\": \"ENABLED\",
        \"groupName\": \"/aws/codebuild/${PROJECT_NAME}\"
      }
    }" > /dev/null

  echo "CodeBuild project created."
fi

# ── Trigger first build ───────────────────────────────────────────────────────
echo ""
echo "Triggering first build..."
BUILD_ID=$(aws codebuild start-build \
  --project-name "$PROJECT_NAME" \
  --region "$REGION" \
  --query 'build.id' \
  --output text)

echo "Build started: $BUILD_ID"
echo "Waiting for build to complete (this takes ~5-8 minutes)..."

while true; do
  STATUS=$(aws codebuild batch-get-builds \
    --ids "$BUILD_ID" \
    --region "$REGION" \
    --query 'builds[0].buildStatus' \
    --output text)

  echo "  Status: $STATUS"

  if [[ "$STATUS" == "SUCCEEDED" ]]; then
    echo "Build SUCCEEDED."
    break
  elif [[ "$STATUS" == "FAILED" || "$STATUS" == "FAULT" || "$STATUS" == "STOPPED" || "$STATUS" == "TIMED_OUT" ]]; then
    echo "ERROR: Build $STATUS. Check logs:"
    echo "  https://console.aws.amazon.com/codesuite/codebuild/projects/${PROJECT_NAME}/build/${BUILD_ID}/log"
    exit 1
  fi

  sleep 20
done

# ── Verify image in ECR ───────────────────────────────────────────────────────
echo ""
echo "Verifying image in ECR..."
aws ecr describe-images \
  --repository-name "$ECR_REPOSITORY" \
  --region "$REGION" \
  --query 'imageDetails[?contains(imageTags, `latest`)].{Tag:imageTags[0],Pushed:imagePushedAt,Size:imageSizeInBytes}' \
  --output table

echo ""
echo "=== Step 0 complete: Docker image is in ECR ==="
echo "Image: ${ECR_REGISTRY}/${ECR_REPOSITORY}:latest"
