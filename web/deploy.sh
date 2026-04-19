#!/usr/bin/env bash
# Build the SPA against the deployed CDN, sync to S3, invalidate CloudFront.
#
# Reads stack outputs (WebBucketName, WebDistributionId, ArticlesDistributionDomain)
# so there are no hardcoded bucket/distribution IDs to drift.
set -euo pipefail

STACK_NAME="${STACK_NAME:-learn-arabic-from-news}"
REGION="${AWS_REGION:-us-east-1}"

cd "$(dirname "$0")"

stack_output() {
  aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" \
    --output text
}

echo "Reading stack outputs from ${STACK_NAME}..."
WEB_BUCKET="$(stack_output WebBucketName)"
DIST_ID="$(stack_output WebDistributionId)"
ARTICLES_DOMAIN="$(stack_output ArticlesDistributionDomain)"

if [[ -z "${WEB_BUCKET}" || -z "${DIST_ID}" || -z "${ARTICLES_DOMAIN}" ]]; then
  echo "Failed to read stack outputs (need WebBucketName, WebDistributionId, ArticlesDistributionDomain)." >&2
  exit 1
fi

CDN_URL="https://${ARTICLES_DOMAIN}"
echo "VITE_CDN_URL=${CDN_URL}"

echo "Installing deps..."
npm ci

echo "Building SPA..."
VITE_CDN_URL="${CDN_URL}" npm run build

echo "Syncing to s3://${WEB_BUCKET}/ ..."
# Hashed assets (Vite emits /assets/<name>-<hash>.<ext>) get the immutable cache;
# everything else (index.html, manifest, icons) stays short-lived so a redeploy
# is visible without waiting for the invalidation alone.
aws s3 sync dist/ "s3://${WEB_BUCKET}/" \
  --region "${REGION}" \
  --delete \
  --exclude "assets/*" \
  --cache-control "public, max-age=300, must-revalidate"

aws s3 sync dist/assets/ "s3://${WEB_BUCKET}/assets/" \
  --region "${REGION}" \
  --delete \
  --cache-control "public, max-age=31536000, immutable"

echo "Invalidating CloudFront ${DIST_ID}..."
aws cloudfront create-invalidation \
  --distribution-id "${DIST_ID}" \
  --paths "/*" \
  --query 'Invalidation.Id' \
  --output text

echo "Frontend deployed: https://$(aws cloudfront get-distribution --id "${DIST_ID}" --query 'Distribution.DomainName' --output text)"
