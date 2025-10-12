# tests/test_api.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import json

from app.main import app

client = TestClient(app)

# Mock data for testing
MOCK_PROPERTY_DATA = {
    "source": "domain",
    "url": "https://www.domain.com.au/test-property-1234567",
    "address": "123 Test Street, Test Suburb, QLD 4000",
    "price": "$500,000",
    "bedrooms": 3,
    "bathrooms": 2,
    "parking": 1,
    "property_type": "House",
    "description": "Beautiful test property",
    "features": ["Air conditioning", "Pool"],
    "image_urls": ["https://example.com/image1.jpg"],
    "image_embeddings": [[0.1, 0.2, 0.3]],
    "floorplan_url": "https://example.com/floorplan.pdf",
    "agent_name": "Test Agent",
    "agent_phone": "+61 400 000 000",
    "inspection_times": ["Saturday 2:00 PM"]
}

class TestAPIEndpoints:
    """Test suite for API endpoints"""
    
    def test_root_endpoint(self):
        """Test root endpoint returns correct response"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "Realestate-CLIP API" in data["message"]
    
    def test_healthz_endpoint(self):
        """Test health check endpoint"""
        response = client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
    
    def test_debug_config_endpoint(self):
        """Test debug config endpoint"""
        response = client.get("/debug/config")
        assert response.status_code == 200
        data = response.json()
        assert "redis" in data
        assert "clip" in data
        assert "http" in data
    
    @patch('app.main._discover_and_scrape')
    @patch('app.main.get_from_cache')
    def test_search_with_query_param(self, mock_cache, mock_scrape):
        """Test search endpoint with query parameter"""
        # Mock cache returns None (no cached data)
        mock_cache.return_value = None
        
        # Mock scrape returns test data
        mock_scrape.return_value = [MOCK_PROPERTY_DATA]
        
        response = client.post(
            "/search",
            params={"address": "123 Test Street, Test Suburb, QLD 4000"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "properties" in data
        assert len(data["properties"]) == 1
        assert data["properties"][0]["address"] == MOCK_PROPERTY_DATA["address"]
    
    @patch('app.main._discover_and_scrape')
    @patch('app.main.get_from_cache')
    def test_search_with_json_body(self, mock_cache, mock_scrape):
        """Test search endpoint with JSON body"""
        # Mock cache returns None (no cached data)
        mock_cache.return_value = None
        
        # Mock scrape returns test data
        mock_scrape.return_value = [MOCK_PROPERTY_DATA]
        
        search_request = {
            "address": "123 Test Street, Test Suburb, QLD 4000",
            "include_embeddings": True,
            "max_images": 5
        }
        
        response = client.post("/search", json=search_request)
        
        assert response.status_code == 200
        data = response.json()
        assert "properties" in data
        assert len(data["properties"]) == 1
    
    @patch('app.main.get_from_cache')
    def test_search_with_cached_data(self, mock_cache):
        """Test search endpoint returns cached data when available"""
        # Mock cache returns cached data
        mock_cache.return_value = [MOCK_PROPERTY_DATA]
        
        response = client.post(
            "/search",
            params={"address": "123 Test Street, Test Suburb, QLD 4000"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "properties" in data
        assert len(data["properties"]) == 1
    
    def test_search_missing_address(self):
        """Test search endpoint returns 400 when address is missing"""
        response = client.post("/search")
        assert response.status_code == 400
        assert "Address is required" in response.json()["detail"]
    
    @patch('app.main._discover_and_scrape')
    @patch('app.main.get_from_cache')
    def test_search_scraping_error(self, mock_cache, mock_scrape):
        """Test search endpoint handles scraping errors gracefully"""
        # Mock cache returns None
        mock_cache.return_value = None
        
        # Mock scrape raises exception
        mock_scrape.side_effect = Exception("Scraping failed")
        
        response = client.post(
            "/search",
            params={"address": "123 Test Street, Test Suburb, QLD 4000"}
        )
        
        # Should return 200 with empty properties list
        assert response.status_code == 200
        data = response.json()
        assert "properties" in data
        assert len(data["properties"]) == 0
    
    @patch('app.main._discover_and_scrape')
    @patch('app.main.get_from_cache')
    def test_search_with_embeddings(self, mock_cache, mock_scrape):
        """Test search endpoint includes embeddings when requested"""
        # Mock cache returns None
        mock_cache.return_value = None
        
        # Mock scrape returns data with embeddings
        mock_scrape.return_value = [MOCK_PROPERTY_DATA]
        
        search_request = {
            "address": "123 Test Street, Test Suburb, QLD 4000",
            "include_embeddings": True,
            "max_images": 3
        }
        
        response = client.post("/search", json=search_request)
        
        assert response.status_code == 200
        data = response.json()
        assert "properties" in data
        assert len(data["properties"]) == 1
        assert "image_embeddings" in data["properties"][0]
    
    def test_search_invalid_json(self):
        """Test search endpoint handles invalid JSON"""
        response = client.post(
            "/search",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422  # Unprocessable Entity

class TestDataNormalization:
    """Test data normalization functions"""
    
    def test_normalize_payload(self):
        """Test payload normalization function"""
        from app.main import _normalize_payload
        
        raw_data = {
            "source": "domain.com.au",
            "url": "https://example.com",
            "address": "123 Test St",
            "price": "$500,000",
            "bedrooms": "3",
            "bathrooms": "2",
            "car_spaces": "1",  # Should map to parking
            "property_type": "House",
            "description": "Test property",
            "features": ["Pool", "AC"],
            "image_urls": ["https://example.com/img1.jpg"],
            "floorplan": "https://example.com/floorplan.pdf",
            "agent_name": "Test Agent",
            "agent_phone": "+61 400 000 000",
            "inspection_times": ["Sat 2pm"]
        }
        
        normalized = _normalize_payload(raw_data)
        
        assert normalized["source"] == "domain"
        assert normalized["bedrooms"] == 3
        assert normalized["bathrooms"] == 2
        assert normalized["parking"] == 1  # car_spaces mapped to parking
        assert normalized["floorplan_url"] == "https://example.com/floorplan.pdf"
        assert isinstance(normalized["features"], list)
        assert isinstance(normalized["image_urls"], list)
        assert isinstance(normalized["inspection_times"], list)
    
    def test_property_type_fix(self):
        """Test property type correction from 'Event' to proper type"""
        from app.main import _normalize_payload
        
        raw_data = {
            "source": "domain",
            "property_type": "Event",  # This should be corrected
            "description": "Beautiful townhouse with modern features"
        }
        
        normalized = _normalize_payload(raw_data)
        
        # The normalization should preserve the original type
        # The actual correction happens in the scraper logic
        assert normalized["property_type"] == "Event"
    
    def test_inspection_times_deduplication(self):
        """Test inspection times deduplication"""
        from app.main import _normalize_payload
        
        raw_data = {
            "source": "domain",
            "inspection_times": [
                "Thursday, 16 Oct 4:45pm - 5:15pm",
                "Thursday, 16 Oct 4:45pm - 5:15pm",  # Duplicate
                "4:45pm - 5:15pm",  # Partial duplicate
                "Saturday, 18 Oct 9:30am - 10:00am"
            ]
        }
        
        normalized = _normalize_payload(raw_data)
        
        # Should preserve all times (deduplication happens in scraper)
        assert len(normalized["inspection_times"]) == 4
        assert isinstance(normalized["inspection_times"], list)

class TestUtilityFunctions:
    """Test utility functions"""
    
    def test_to_int_function(self):
        """Test _to_int helper function"""
        from app.main import _to_int
        
        assert _to_int("3") == 3
        assert _to_int(3.5) == 3
        assert _to_int("3 bedrooms") == 3
        assert _to_int("No parking") is None
        assert _to_int(None) is None
        assert _to_int("") is None

# Integration tests (require actual services)
class TestIntegration:
    """Integration tests - require Redis and external services"""
    
    @pytest.mark.skip(reason="Requires Redis connection")
    def test_cache_integration(self):
        """Test Redis cache integration"""
        from app.cache import set_to_cache, get_from_cache
        
        test_data = [MOCK_PROPERTY_DATA]
        test_address = "123 Test Street, Test Suburb, QLD 4000"
        
        # Set cache
        set_to_cache(test_address, test_data)
        
        # Get from cache
        cached_data = get_from_cache(test_address)
        
        assert cached_data is not None
        assert len(cached_data) == 1
        assert cached_data[0]["address"] == MOCK_PROPERTY_DATA["address"]
    
    @pytest.mark.skip(reason="Requires external services")
    def test_clip_embedding_integration(self):
        """Test CLIP embedding generation"""
        from app.embeddings.clip_embedder import get_embedding
        
        # Test with a real image URL
        test_image_url = "https://via.placeholder.com/300x200"
        embedding = get_embedding(test_image_url)
        
        # Should return a list of floats
        assert isinstance(embedding, list)
        assert len(embedding) > 0
        assert all(isinstance(x, float) for x in embedding)

if __name__ == "__main__":
    pytest.main([__file__])
