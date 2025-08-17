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

{
  "address": "107/131 Sir Fred Schonell Drive, St Lucia, Qld 4067",
  "include_embeddings": true,
  "max_images": 12
}
