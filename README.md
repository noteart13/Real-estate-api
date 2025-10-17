# 🏠 Real Estate CLIP API

FastAPI service that searches and analyzes real estate properties using web scraping and AI-powered image embeddings.

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://docker.com)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-GKE-orange.svg)](https://kubernetes.io)

## 🚀 Features

- **🔍 Intelligent Property Search**: Automatically searches property addresses across major Australian real estate platforms
- **🏢 Multi-Platform Support**: Integrated scrapers for `domain.com.au` and `realestate.com.au`
- **🤖 AI-Powered Analysis**: Extracts semantic embeddings from property images using OpenAI's CLIP model
- **⚡ High Performance**: Redis caching and async processing for optimal response times
- **🐳 Production Ready**: Dockerized with Kubernetes deployment manifests
- **📊 Comprehensive API**: RESTful endpoints with automatic OpenAPI documentation
- **🔒 Enterprise Security**: Non-root containers, proper secrets management, and CORS support

## 🏗️ Architecture

High-level architecture: Client → FastAPI → Scrapers (Domain/REA) → Normalization → CLIP Embeddings → Redis Cache → JSON Response.

## 📋 Prerequisites

- Python 3.11 (required for PyTorch compatibility)
- Redis (for response caching)
- Docker (for containerization)
- Google Cloud SDK (for deployment)
- kubectl (for Kubernetes management)

## 🛠️ Quick Start

### Local Development
```bash
# Clone and setup
git clone <repository-url>
cd realestate-clip-api
python3.11 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start Redis (required)
# macOS: brew install redis && brew services start redis
# Ubuntu: sudo apt install redis-server && sudo systemctl start redis

# Run API
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Access**: http://localhost:8000/docs

### Docker Deployment
```bash
# Build and run
docker build -t realestate-clip-api:latest .
docker run --rm -p 8000:8000 \
  -e REDIS_HOST=host.docker.internal \
  -e SCRAPINGBEE_API_KEY="YOUR_KEY" \
  -e RESPECT_ROBOTS_TXT=0 \
  --name realestate-api \
  realestate-clip-api:latest
```

### Google Cloud Deployment
```bash
# Quick deployment (see DEMO.md for detailed steps)
gcloud auth login
gcloud config set project PROJECT_ID
gcloud services enable artifactregistry.googleapis.com
gcloud artifacts repositories create property-repo --repository-format=docker --location=australia-southeast1
gcloud auth configure-docker australia-southeast1-docker.pkg.dev

# Build and push
docker build -t realestate-clip-api:latest .
docker tag realestate-clip-api:latest australia-southeast1-docker.pkg.dev/PROJECT_ID/property-repo/realestate-clip-api:latest
docker push australia-southeast1-docker.pkg.dev/PROJECT_ID/property-repo/realestate-clip-api:latest

# Deploy to GKE
gcloud container clusters get-credentials CLUSTER_NAME --region=australia-southeast1 --project=PROJECT_ID
kubectl apply -f kubernetes/resources.yaml
kubectl get service property-service -n property-ns
```

## 📊 API Response Example
```json
{
  "properties": [
    {
      "source": "domain",
      "url": "https://www.domain.com.au/...",
      "address": "107/131 Sir Fred Schonell Drive, St Lucia, QLD 4067",
      "price": "$550,000",
      "bedrooms": 2,
      "bathrooms": 2,
      "parking": 1,
      "property_type": "Apartment",
      "description": "Modern apartment...",
      "features": ["Air conditioning", "Pool"],
      "image_urls": ["https://..."],
      "image_embeddings": [[0.123, 0.456, ...]]
    }
  ]
}
```

## 🔴 Error Codes
- `400`: Invalid address format
- `404`: No property found
- `429`: Rate limit exceeded
- `503`: Service temporarily unavailable

### Other Endpoints
- **Health**: `GET /healthz`
- **Config**: `GET /debug/config`
- **Cache**: `GET /debug/cache`

## 🔧 Configuration

### Environment Variables
| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_HOST` | Redis server hostname | `localhost` |
| `REDIS_PORT` | Redis server port | `6379` |
| `REQUEST_TIMEOUT` | HTTP timeout (seconds) | `60` |
| `RESPECT_ROBOTS_TXT` | Respect robots.txt (0/1) | `1` |
| `SCRAPINGBEE_API_KEY` | ScrapingBee API key | Required |

### Request Parameters
- `address`: Property address or direct URL
- `include_embeddings`: Generate CLIP embeddings (true/false)
- `max_images`: Maximum images to process (1-50)
- `strict_match`: Require exact address match (true/false)
- `allow_near`: Allow near matches when no exact match (true/false)

## 🧪 Testing

```bash
# Health check
curl http://localhost:8000/healthz

# Search test
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"address":"3/106 Carmody Road St Lucia QLD 4067","include_embeddings":false,"max_images":12}'

# Run tests
python -m pytest tests/ -v
```

## 📞 Support

- **API Docs**: http://localhost:8000/docs (local) or http://EXTERNAL_IP/docs (deployed)
- **Detailed Demo**: See [DEMO.md](DEMO.md) for step-by-step deployment guide
- **Issues**: Create GitHub issue
- **Health**: http://localhost:8000/healthz

---

**Built with ❤️ for intelligent real estate analysis**