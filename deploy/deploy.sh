#!/usr/bin/env bash
# Usage: ./deploy/deploy.sh
#
# Required env vars (set in CI/CD or export before running):
#   AWS_ACCOUNT_ID   — your 12-digit AWS account ID
#   AWS_REGION       — e.g. us-east-1
#   ECR_REPO         — ECR repository name, e.g. auditsmart-quantum
#   ECS_CLUSTER      — ECS cluster name
#   ECS_SERVICE      — ECS service name
#
# Optional:
#   IMAGE_TAG        — Docker image tag (default: git SHA)
set -euo pipefail

: "${AWS_ACCOUNT_ID:?must be set}"
: "${AWS_REGION:?must be set}"
: "${ECR_REPO:?must be set}"
: "${ECS_CLUSTER:?must be set}"
: "${ECS_SERVICE:?must be set}"

TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD)}"
REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE="${REGISTRY}/${ECR_REPO}:${TAG}"
IMAGE_LATEST="${REGISTRY}/${ECR_REPO}:latest"

echo "==> Building Docker image: ${IMAGE}"
docker build -t "${IMAGE}" -t "${IMAGE_LATEST}" .

echo "==> Authenticating with ECR"
aws ecr get-login-password --region "${AWS_REGION}" \
    | docker login --username AWS --password-stdin "${REGISTRY}"

echo "==> Pushing image to ECR"
docker push "${IMAGE}"
docker push "${IMAGE_LATEST}"

echo "==> Updating ECS service: ${ECS_CLUSTER}/${ECS_SERVICE}"
aws ecs update-service \
    --cluster "${ECS_CLUSTER}" \
    --service  "${ECS_SERVICE}" \
    --force-new-deployment \
    --region "${AWS_REGION}" \
    --query 'service.{status:status,desiredCount:desiredCount}' \
    --output table

echo ""
echo "Deployment triggered. Monitor at:"
echo "  https://${AWS_REGION}.console.aws.amazon.com/ecs/v2/clusters/${ECS_CLUSTER}/services/${ECS_SERVICE}"
