# Step to run Projects
python -m venv .venv
# MAC/Linux: source .venv/bin/activate     
# Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Install Redis server
# https://github.com/microsoftarchive/redis
Then extract file and choose redis-server file to run the redis server

# RUN API
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# http://127.0.0.1:8000/docs#

## API Endpoints
# POST /search
# Search properties by address

# Request:

json
{
  "address": "107/131 Sir Fred Schonell Drive, St Lucia, Qld 4067"
}
Successful Response:

json
{
  "properties": [
    {
      "source": "domain",
      "address": "107/131 Sir Fred Schonell Drive, St Lucia QLD 4067",
      "price": "$700,000",
      "bedrooms": 2,
      "bathrooms": 2,
      "parking": 1,
      "property_type": "Apartment",
      "description": "This expansive two-bedroom apartment...",
      "features": ["Secure Parking", "Air conditioning"],
      "image_urls": ["https://...", ...],
      "floorplan_url": "https://...",
      "image_embeddings": [[0.123, ...], ...]
    },
    {
      "source": "realestate",
      ...
    }
  ]
}