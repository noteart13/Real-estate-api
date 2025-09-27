## Realestate-CLIP API
FastAPI service that:
- Searches a property address on domain.com.au and realestate.com.au
- Scrapes listing details and image URLs
- Extracts image embeddings using OpenAI CLIP (ViT-B/32)

### Requirements
- Python 3.11 (local) — matches Docker base. Python 3.13 on Windows will fail to install NumPy/PyTorch wheels.
- Redis (for response caching)
- Optional: Docker, Google Cloud SDK, kubectl (for deployment)

### Setup (local)
Windows (recommended):
```powershell
py -3.11 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -U pip
pip install -r requirements.txt
```

Mac/Linux:
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

### Install Redis
- Windows: download from `https://github.com/microsoftarchive/redis`, extract và chạy `redis-server`
- Mac: `brew install redis && brew services start redis`
- Linux: `sudo apt install redis-server`

### Run API
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Useful URLs:
- Root: `http://127.0.0.1:8000/`
- Docs (Swagger): `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/healthz`
- Config: `http://127.0.0.1:8000/debug/config`

### Example request (POST /search)
```json
{
  "address": "107/131 Sir Fred Schonell Drive, St Lucia, Qld 4067",
  "include_embeddings": true,
  "max_images": 12
}
```

Notes:
- You can also pass a direct listing URL as the `address` to skip search.
- `include_embeddings=false` speeds up responses for quick checks.

### Environment variables (.env)
Tạo file `.env` ở thư mục gốc với nội dung ví dụ:
```ini
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
CACHE_TTL=172800

# Scraping
USER_AGENT=Mozilla/5.0 (compatible; PropertyScraper/1.0)
REQUEST_TIMEOUT=60
RESPECT_ROBOTS_TXT=0
CRAWL_DELAY=1

# Fallback provider (bạn cung cấp key ở đây)
SCRAPINGBEE_API_KEY=M1XFCD1X0LVQJHIXT6BBFZGWFTSSFEQDF8CDGZDKUX0QVPPU5Y1TZOAD6HSHRA95BIGPBZE7T2G0JDZD
```

Khi chạy Docker, có thể truyền trực tiếp:
```powershell
docker run --rm -p 8000:8000 `
  -e REDIS_HOST=host.docker.internal `
  -e SCRAPINGBEE_API_KEY="M1XFCD1X0LVQJHIXT6BBFZGWFTSSFEQDF8CDGZDKUX0QVPPU5Y1TZOAD6HSHRA95BIGPBZE7T2G0JDZD" `
  -e RESPECT_ROBOTS_TXT=0 `
  -e REQUEST_TIMEOUT=90 `
  --name property-api property-api:local `
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

---

## Troubleshooting
- NumPy/PyTorch install errors on Windows: ensure Python 3.11 and upgrade pip (`pip install -U pip`).
- 404 at `/`: the service exposes `/` (root), `/docs`, `/healthz`, `/debug/config`.
- Rate limits/403 while scraping: set `SCRAPINGBEE_API_KEY` (see `kubernetes/resources.yaml`) for fallback fetching.
