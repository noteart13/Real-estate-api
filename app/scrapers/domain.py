from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
import re
from .utils import (
    fetch_url, clean_text, clean_price, jsonld_blocks,
    to_int_opt, extract_images_generic, filter_photo_urls, first_href
)

_IGNORED_JSONLD_TYPES = {
    "FAQPage", "BreadcrumbList", "Organization", "WebPage", "WebSite",
}


def _select_property_type(raw_type) -> Optional[str]:
    if isinstance(raw_type, list):
        types = [str(x) for x in raw_type if str(x) not in _IGNORED_JSONLD_TYPES]
        return types[0] if types else None
    if isinstance(raw_type, str) and raw_type not in _IGNORED_JSONLD_TYPES:
        return raw_type
    return None


def _extract_int_via_regex(html: str, patterns: List[re.Pattern]) -> Optional[int]:
    for pat in patterns:
        m = pat.search(html)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                continue
    return None


def scrape_domain(url: str) -> Optional[Dict[str, Any]]:
    soup = fetch_url(url, ignore_robots=True, max_retries=1, render_js=False)
    if not soup:
        return None

    item: Dict[str, Any] = {"source": "domain", "url": url}

    # --- JSON-LD ưu tiên ---
    for blk in jsonld_blocks(soup):
        # Address
        addr = blk.get("address")
        if isinstance(addr, dict):
            parts = [addr.get("streetAddress"), addr.get("addressLocality"),
                     addr.get("addressRegion"), addr.get("postalCode")]
            s = clean_text(" ".join([p for p in parts if p]))
            if s: item["address"] = s
        elif isinstance(addr, str):
            item["address"] = clean_text(addr)

        # Price
        price = blk.get("price")
        if not price and isinstance(blk.get("offers"), dict):
            price = blk["offers"].get("price") or blk["offers"].get("priceSpecification", {}).get("price")
        if price:
            item["price"] = clean_price(str(price))

        # Rooms
        item["bedrooms"]  = item.get("bedrooms")  or to_int_opt(blk.get("numberOfBedrooms") or blk.get("bedrooms"))
        item["bathrooms"] = item.get("bathrooms") or to_int_opt(blk.get("numberOfBathroomsTotal") or blk.get("bathrooms"))
        item["parking"]   = item.get("parking")   or to_int_opt(blk.get("carSpaces") or blk.get("numberOfParkingSpaces"))

        # Type
        ptype = _select_property_type(blk.get("propertyType") or blk.get("@type"))
        if ptype:
            item["property_type"] = ptype

        # Desc
        if isinstance(blk.get("description"), str):
            item["description"] = clean_text(blk["description"])

        # Images
        imgs = blk.get("image") or blk.get("images")
        if isinstance(imgs, list):
            item.setdefault("image_urls", []).extend([u for u in imgs if isinstance(u, str) and u.startswith("http")])
        elif isinstance(imgs, str) and imgs.startswith("http"):
            item.setdefault("image_urls", []).append(imgs)

    # --- Fallbacks HTML ---
    if not item.get("address"):
        h1 = soup.select_one('h1[data-testid="address"]')
        if h1:
            item["address"] = clean_text(h1.get_text(" ", strip=True))

    if not item.get("price"):
        # Try multiple selectors for price
        price_selectors = [
            'div[data-testid="listing-details__summary-title"]',
            '.css-1texeil',  # Price display class
            '[data-testid="price"]',
            '.listing-details__summary-title',
            'h1[data-testid="listing-details__summary-title"]'
        ]
        
        for selector in price_selectors:
            price_elem = soup.select_one(selector)
            if price_elem:
                price_text = clean_price(price_elem.get_text(" ", strip=True))
                if price_text and price_text != "Contact agent":
                    item["price"] = price_text
                    break
        
        # If still no price, try to find "Offers Above" text
        if not item.get("price"):
            offers_text = soup.find(text=re.compile(r"Offers Above", re.I))
            if offers_text:
                parent = offers_text.parent
                if parent:
                    item["price"] = clean_price(parent.get_text(" ", strip=True))

    if not item.get("description"):
        # Try multiple selectors for description
        desc_selectors = [
            "meta[name='description']",
            "meta[property='og:description']",
            '[data-testid="listing-summary__description"]',
            '.listing-summary__description',
            '.property-description',
            '.description'
        ]
        
        for selector in desc_selectors:
            desc_elem = soup.select_one(selector)
            if desc_elem:
                if desc_elem.name == 'meta':
                    desc_text = desc_elem.get("content", "")
                else:
                    desc_text = desc_elem.get_text(" ", strip=True)
                
                if desc_text and len(desc_text) > 20:  # Avoid short descriptions
                    item["description"] = clean_text(desc_text)
                    break

    if not item.get("image_urls"):
        item["image_urls"] = extract_images_generic(soup)
    item["image_urls"] = filter_photo_urls(item.get("image_urls", []))[:40]

    # Features - improved extraction
    feats = []
    feature_selectors = [
        "div[data-testid='listing-details__features'] li",
        ".property-features li",
        ".features li",
        "[data-testid*='feature'] li",
        ".listing-features li"
    ]
    
    for selector in feature_selectors:
        for el in soup.select(selector):
            t = clean_text(el.get_text(" ", strip=True))
            if t and len(t) > 2 and t not in feats:
                feats.append(t)
        if feats:
            break
    
    # Also try to extract from text patterns
    if not feats:
        page_text = soup.get_text()
        common_features = [
            "Air conditioning", "Built in wardrobes", "Internal Laundry", 
            "Secure Parking", "Dishwasher", "Solar panels", "Pets Allowed",
            "Swimming Pool", "Garden", "Balcony", "Study", "Ensuite"
        ]
        for feature in common_features:
            if feature.lower() in page_text.lower():
                feats.append(feature)
    
    if feats: 
        item["features"] = feats[:50]

    # Floorplan
    # Domain thường có link riêng
    fp = soup.select_one("a[data-testid='floorplan-link']")
    if fp and fp.get("href"):
        item["floorplan_url"] = fp["href"]

    # Agent - improved extraction
    agent_selectors = [
        "a[data-testid='listing-details__agent-name']",
        "[data-testid*='agent-name']",
        ".agent-name",
        ".listing-agent",
        ".property-agent"
    ]
    
    for selector in agent_selectors:
        an = soup.select_one(selector)
        if an:
            item["agent_name"] = clean_text(an.get_text(" ", strip=True))
            break
    
    # Agent phone - improved extraction
    phone_selectors = [
        "a[data-testid='agent-phone']",
        "[data-testid*='agent-phone']",
        ".agent-phone",
        ".listing-agent-phone",
        "a[href^='tel:']"
    ]
    
    for selector in phone_selectors:
        ap = soup.select_one(selector)
        if ap:
            phone_text = ap.get_text(" ", strip=True) or ap.get("href", "").replace("tel:", "")
            if phone_text:
                item["agent_phone"] = clean_text(phone_text)
                break

    # Inspections - improved extraction with deduplication
    times = []
    seen_times = set()
    
    # Try multiple selectors for inspection times
    inspection_selectors = [
        "div[data-testid='inspection-times'] time",
        "div[data-testid='inspection-times']",
        ".inspection-times time",
        ".inspection-times",
        "[data-testid*='inspection'] time",
        "[data-testid*='inspection']"
    ]
    
    for selector in inspection_selectors:
        for tim in soup.select(selector):
            if tim.get("datetime"):
                time_str = tim["datetime"]
                if time_str not in seen_times:
                    times.append(time_str)
                    seen_times.add(time_str)
            elif tim.get_text(strip=True):
                # Extract text content if no datetime attribute
                text = clean_text(tim.get_text(strip=True))
                if text and ("am" in text.lower() or "pm" in text.lower() or ":" in text):
                    # Clean up the text to avoid duplicates
                    clean_text_time = re.sub(r'\s+', ' ', text).strip()
                    if clean_text_time not in seen_times and len(clean_text_time) < 100:
                        times.append(clean_text_time)
                        seen_times.add(clean_text_time)
        if times:
            break
    
    # If no structured times found, try to extract from page text
    if not times:
        page_text = soup.get_text()
        # Look for time patterns like "Thursday, 16 Oct 4:45pm - 5:15pm"
        time_patterns = [
            r'([A-Za-z]+day,?\s+\d+\s+[A-Za-z]+\s+\d+:\d+[ap]m\s*-\s*\d+:\d+[ap]m)',
            r'([A-Za-z]+day,?\s+\d+\s+[A-Za-z]+\s+\d+:\d+[ap]m)',
            r'(\d+:\d+[ap]m\s*-\s*\d+:\d+[ap]m)',
            r'(\d+:\d+[ap]m)'
        ]
        
        for pattern in time_patterns:
            matches = re.findall(pattern, page_text, re.I)
            for match in matches:
                clean_match = re.sub(r'\s+', ' ', match).strip()
                if clean_match not in seen_times and len(clean_match) < 50:
                    times.append(clean_match)
                    seen_times.add(clean_match)
    
    if times: 
        item["inspection_times"] = times[:10]  # Limit to 10 inspection times

    # --- Property Type (if not already extracted) ---
    if not item.get("property_type") or item.get("property_type") == "Event":
        # Try to extract property type from HTML
        type_selectors = [
            '[data-testid="listing-summary__property-type"]',
            '.listing-summary__property-type',
            '.property-type',
            'h1[data-testid="address"] + div',
            '.css-1texeil + div'
        ]
        
        for selector in type_selectors:
            type_elem = soup.select_one(selector)
            if type_elem:
                type_text = type_elem.get_text(" ", strip=True).lower()
                if any(word in type_text for word in ['townhouse', 'house', 'apartment', 'unit', 'villa', 'duplex']):
                    item["property_type"] = type_text.title()
                    break
        
        # Fallback: look for property type in text
        if not item.get("property_type") or item.get("property_type") == "Event":
            page_text = soup.get_text().lower()
            if 'townhouse' in page_text:
                item["property_type"] = "Townhouse"
            elif 'house' in page_text:
                item["property_type"] = "House"
            elif 'apartment' in page_text:
                item["property_type"] = "Apartment"

    # --- Heuristics: bedrooms/bathrooms/parking via embedded JSON or visible text ---
    if not (item.get("bedrooms") and item.get("bathrooms") and item.get("parking")):
        html = str(soup)
        beds = _extract_int_via_regex(html, [
            re.compile(r'"(?:numberOfBedrooms|bedrooms|beds)"\s*:\s*(\d+)', re.I),
            re.compile(r'"bedroomCount"\s*:\s*(\d+)', re.I),
        ])
        baths = _extract_int_via_regex(html, [
            re.compile(r'"(?:numberOfBathroomsTotal|bathrooms|baths)"\s*:\s*(\d+)', re.I),
            re.compile(r'"bathroomCount"\s*:\s*(\d+)', re.I),
        ])
        cars = _extract_int_via_regex(html, [
            re.compile(r'"(?:carSpaces|numberOfParkingSpaces)"\s*:\s*(\d+)', re.I),
            re.compile(r'"car[s ]?space[s]?"\s*:\s*(\d+)', re.I),
        ])

        # If still missing, parse visible shorthand like "3 bed", "2 bath", "1 car"
        text_blob = clean_text(soup.get_text(" ", strip=True)).lower()
        if beds is None:
            m = re.search(r'(\d+)\s*(?:bed|beds|bedroom)', text_blob)
            if m: beds = int(m.group(1))
        if baths is None:
            m = re.search(r'(\d+)\s*(?:bath|baths|bathroom)', text_blob)
            if m: baths = int(m.group(1))
        if cars is None:
            m = re.search(r'(\d+)\s*(?:car|cars|parking|garage)', text_blob)
            if m: cars = int(m.group(1))

        if beds is not None:
            item["bedrooms"] = beds
        if baths is not None:
            item["bathrooms"] = baths
        if cars is not None:
            item["parking"] = cars

    # Additional property details
    # Property size/land area
    size_selectors = [
        "[data-testid*='property-size']",
        "[data-testid*='land-area']",
        ".property-size",
        ".land-area",
        ".property-details .size"
    ]
    
    for selector in size_selectors:
        size_el = soup.select_one(selector)
        if size_el:
            size_text = clean_text(size_el.get_text(strip=True))
            if size_text and ("m²" in size_text or "sqm" in size_text.lower()):
                item["property_size"] = size_text
                break
    
    # Property status (For Sale, Under Contract, etc.)
    status_selectors = [
        "[data-testid*='listing-status']",
        "[data-testid*='property-status']",
        ".listing-status",
        ".property-status",
        ".status-badge"
    ]
    
    for selector in status_selectors:
        status_el = soup.select_one(selector)
        if status_el:
            status_text = clean_text(status_el.get_text(strip=True))
            if status_text:
                item["listing_status"] = status_text
                break
    
    # Price guide/range
    price_guide_selectors = [
        "[data-testid*='price-guide']",
        "[data-testid*='price-range']",
        ".price-guide",
        ".price-range",
        ".estimated-price"
    ]
    
    for selector in price_guide_selectors:
        price_el = soup.select_one(selector)
        if price_el:
            price_text = clean_text(price_el.get_text(strip=True))
            if price_text and ("guide" in price_text.lower() or "range" in price_text.lower()):
                item["price_guide"] = price_text
                break
    
    # Agency information
    agency_selectors = [
        "[data-testid*='agency']",
        "[data-testid*='real-estate']",
        ".agency-name",
        ".real-estate-agency",
        ".listing-agency"
    ]
    
    for selector in agency_selectors:
        agency_el = soup.select_one(selector)
        if agency_el:
            agency_text = clean_text(agency_el.get_text(strip=True))
            if agency_text:
                item["agency_name"] = agency_text
                break
    
    # Property ID/Listing ID
    listing_id_patterns = [
        r'listing[_-]?id["\']?\s*[:=]\s*["\']?(\d+)',
        r'property[_-]?id["\']?\s*[:=]\s*["\']?(\d+)',
        r'id["\']?\s*[:=]\s*["\']?(\d{8,})'
    ]
    
    html_content = str(soup)
    for pattern in listing_id_patterns:
        match = re.search(pattern, html_content, re.I)
        if match:
            item["listing_id"] = match.group(1)
            break
    
    # Days on market
    dom_selectors = [
        "[data-testid*='days-on-market']",
        "[data-testid*='dom']",
        ".days-on-market",
        ".dom"
    ]
    
    for selector in dom_selectors:
        dom_el = soup.select_one(selector)
        if dom_el:
            dom_text = clean_text(dom_el.get_text(strip=True))
            if dom_text and ("day" in dom_text.lower() or "dom" in dom_text.lower()):
                item["days_on_market"] = dom_text
                break

    return item
