## Step to run Projects
IMPORTANT: Use Python 3.11 locally (matches Docker base). Python 3.13 will fail to install NumPy/PyTorch wheels on Windows.
# Windows (recommended)
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Mac/Linux
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

## Install Redis server
# https://github.com/microsoftarchive/redis
Then extract file and choose redis-server file to run the redis server

## RUN API
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# http://127.0.0.1:8000/docs#

## API Endpoints
# Search properties by address

{
  "address": "107/131 Sir Fred Schonell Drive, St Lucia, Qld 4067",
  "include_embeddings": true,
  "max_images": 12
}
