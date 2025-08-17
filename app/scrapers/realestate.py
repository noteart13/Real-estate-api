from bs4 import BeautifulSoup
from .utils import fetch_url, clean_text, clean_price
import logging
import re
import json

logger = logging.getLogger(__name__)

def scrape_realestate(url: str) -> dict:
    soup = fetch_url(url)
    if not soup:
        return None

    try:
        # Xác định property type từ URL
        property_type = "Property"
        if "/property-apartment-" in url:
            property_type = "Apartment"
        elif "/property-unit-" in url:
            property_type = "Unit"
        elif "/property-townhouse-" in url:
            property_type = "Townhouse"
        elif "/property-house-" in url:
            property_type = "House"
        
        # Lấy thông tin cơ bản
        address_elem = soup.select_one('h1.property-info-address')
        price_elem = soup.select_one('div.property-price')
        
        # Lấy thông số phòng
        bedrooms = soup.select_one('.rui-icon-bed + span')
        bathrooms = soup.select_one('.rui-icon-bath + span')
        parking = soup.select_one('.rui-icon-car + span')
        
        data = {
            "source": "realestate.com.au",
            "url": url,
            "address": clean_text(address_elem.text) if address_elem else "N/A",
            "price": clean_price(price_elem.text) if price_elem else "Contact agent",
            "bedrooms": extract_number(bedrooms.text) if bedrooms else "N/A",
            "bathrooms": extract_number(bathrooms.text) if bathrooms else "N/A",
            "parking": extract_number(parking.text) if parking else "N/A",
            "property_type": property_type,
            "description": clean_text(soup.select_one('div.property-info__description').text) 
                           if soup.select_one('div.property-info__description') else "N/A",
            "features": [clean_text(feature.text) for feature in soup.select('ul.property-features li')] 
                        if soup.select_one('ul.property-features') else [],
            "image_urls": extract_image_urls(soup),
            "floorplan": extract_floorplan(soup),
            "agent_name": clean_text(soup.select_one('.realestate-agent__name').text) 
                         if soup.select_one('.realestate-agent__name') else "N/A",
            "agent_phone": clean_text(soup.select_one('.realestate-agent__phone').text) 
                          if soup.select_one('.realestate-agent__phone') else "N/A",
            "inspection_times": extract_inspection_times(soup),
        }
        return data
    except Exception as e:
        logger.error(f"Error scraping Realestate: {str(e)}", exc_info=True)
        return None

# Hàm hỗ trợ
def extract_number(text: str) -> str:
    if not text:
        return "N/A"
    
    # Tìm số nguyên trong chuỗi
    match = re.search(r'\d+', text)
    return match.group(0) if match else "N/A"

def extract_image_urls(soup):
    images = []
    # Tìm ảnh trong cả gallery và carousel
    for img in soup.select('div[data-testid="gallery"] img, div.carousel img'):
        src = img.get('src')
        if src and src.startswith('http'):
            # Chuyển URL proxy thành URL gốc nếu cần
            if "images.domain" in src:
                src = src.split("?")[0]
            images.append(src)
    return images

def extract_floorplan(soup):
    floorplan = soup.select_one('a:has(span:contains("Floorplan"))')
    return floorplan['href'] if floorplan and 'href' in floorplan.attrs else None

def extract_inspection_times(soup):
    times = []
    for time_elem in soup.select('div.inspection-times time'):
        if 'datetime' in time_elem.attrs:
            times.append(time_elem['datetime'])
    return times