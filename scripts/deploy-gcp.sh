<<'DEPLOY_SCRIPT'
#!/bin/bash
set -e

echo "🚀 Deploying Arbitrage Bot to Google Cloud Platform..."

# Variables
PROJECT_ID="${GCP_PROJECT_ID:-your-gcp-project-id}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="arb-bot"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Check gcloud
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI not found. Install it first."
    exit 1
fi

# Build Docker image
echo "📦 Building Docker image..."
docker build -t ${IMAGE_NAME} .

# Push to GCR
echo "⬆️  Pushing to Google Container Registry..."
docker push ${IMAGE_NAME}

# Deploy to Cloud Run
echo "☁️  Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
  --image ${IMAGE_NAME} \
  --platform managed \
  --region ${REGION} \
  --memory 1Gi \
  --cpu 2 \
  --timeout 3600 \
  --max-instances 1 \
  --min-instances 1 \
  --no-allow-unauthenticated \
  --set-env-vars ENVIRONMENT=production

echo "✅ Deployment complete!"
echo "📊 Check logs: gcloud run logs read --service=${SERVICE_NAME}"
DEPLOY_SCRIPT