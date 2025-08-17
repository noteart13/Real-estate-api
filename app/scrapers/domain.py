#domain.py
from bs4 import BeautifulSoup
from .utils import fetch_url, clean_text, clean_price
import logging
import re
logger = logging.getLogger(__name__)
def scrape_domain(url: str) -> dict:
    soup = fetch_url(url)
    if not soup:
        return None

    try:
        # Xác định property type từ URL
        property_type = "Property"
        if "/apartment/" in url or "/unit/" in url:
            property_type = "Apartment/Unit"
        elif "/townhouse/" in url:
            property_type = "Townhouse"
        elif "/house/" in url:
            property_type = "House"
        
        # Lấy thông tin cơ bản
        address_elem = soup.select_one('h1[data-testid="address"]')
        price_elem = soup.select_one('[data-testid="price"]')
        
        # Lấy thông số phòng
        features = soup.select('[data-testid="property-features"] > div')
        bedrooms = features[0].get_text(strip=True) if len(features) > 0 else "N/A"
        bathrooms = features[1].get_text(strip=True) if len(features) > 1 else "N/A"
        parking = features[2].get_text(strip=True) if len(features) > 2 else "N/A"
        
        data = {
            "source": "domain.com.au",
            "url": url,
            "address": clean_text(address_elem.text) if address_elem else "N/A",
            "price": clean_price(price_elem.text) if price_elem else "Contact agent",
            "bedrooms": extract_number(bedrooms),
            "bathrooms": extract_number(bathrooms),
            "parking": extract_number(parking),
            "property_type": property_type,
            "description": clean_text(soup.select_one('[data-testid="listing-details__description"]').text) 
                           if soup.select_one('[data-testid="listing-details__description"]') else "N/A",
            "features": [clean_text(feature.text) for feature in soup.select('div[data-testid="listing-details__features"] li')] 
                        if soup.select_one('div[data-testid="listing-details__features"]') else [],
            "image_urls": extract_image_urls(soup),
            "floorplan": extract_floorplan(soup),
            "agent_name": clean_text(soup.select_one('a[data-testid="listing-details__agent-name"]').text) 
                         if soup.select_one('a[data-testid="listing-details__agent-name"]') else "N/A",
            "agent_phone": clean_text(soup.select_one('a[data-testid="agent-phone"]').text) 
                          if soup.select_one('a[data-testid="agent-phone"]') else "N/A",
            "inspection_times": extract_inspection_times(soup),
        }
        return data
    except Exception as e:
        logger.error(f"Error scraping Domain: {str(e)}", exc_info=True)
        return None

# Hàm hỗ trợ mới
def extract_number(text: str) -> str:
    if not text:
        return "N/A"
    
    # Tìm số nguyên trong chuỗi
    match = re.search(r'\d+', text)
    return match.group(0) if match else "N/A"

def extract_image_urls(soup):
    images = []
    # Tìm cả thẻ meta và img
    for img in soup.select('img[data-testid="gallery-image-img"], meta[itemprop="image"]'):
        src = img.get('src') or img.get('content')
        if src and src.startswith('http'):
            images.append(src)
    return images

def extract_floorplan(soup):
    floorplan = soup.select_one('a[data-testid="floorplan-link"]')
    return floorplan['href'] if floorplan and 'href' in floorplan.attrs else None

def extract_inspection_times(soup):
    times = []
    for time_elem in soup.select('div[data-testid="inspection-times"] time'):
        if 'datetime' in time_elem.attrs:
            times.append(time_elem['datetime'])
    return times