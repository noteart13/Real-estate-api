from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
import re
from .utils import (
    fetch_url, clean_text, clean_price, jsonld_blocks,
    to_int_opt, extract_images_generic, filter_photo_urls
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


def scrape_realestate(url: str) -> Optional[Dict[str, Any]]:
    soup = fetch_url(url, ignore_robots=True, max_retries=1, render_js=False)
    if not soup:
        return None

    item: Dict[str, Any] = {"source": "realestate", "url": url}

    # --- JSON-LD ưu tiên ---
    for blk in jsonld_blocks(soup):
        addr = blk.get("address")
        if isinstance(addr, dict):
            s = clean_text(" ".join([addr.get(k, "") for k in ("streetAddress","addressLocality","addressRegion","postalCode")]))
            if s: item["address"] = s
        elif isinstance(addr, str):
            item["address"] = clean_text(addr)

        price = blk.get("price")
        if not price and isinstance(blk.get("offers"), dict):
            price = blk["offers"].get("price") or blk["offers"].get("priceSpecification", {}).get("price")
        if price:
            item["price"] = clean_price(str(price))

        item["bedrooms"]  = item.get("bedrooms")  or to_int_opt(blk.get("numberOfBedrooms") or blk.get("bedrooms"))
        item["bathrooms"] = item.get("bathrooms") or to_int_opt(blk.get("numberOfBathroomsTotal") or blk.get("bathrooms"))
        item["parking"]   = item.get("parking")   or to_int_opt(blk.get("carSpaces") or blk.get("numberOfParkingSpaces"))

        ptype = _select_property_type(blk.get("propertyType") or blk.get("@type"))
        if ptype:
            item["property_type"] = ptype

        if isinstance(blk.get("description"), str):
            item["description"] = clean_text(blk["description"])

        imgs = blk.get("image") or blk.get("images")
        if isinstance(imgs, list):
            item.setdefault("image_urls", []).extend([u for u in imgs if isinstance(u, str) and u.startswith("http")])
        elif isinstance(imgs, str) and imgs.startswith("http"):
            item.setdefault("image_urls", []).append(imgs)

    # --- Fallbacks HTML ---
    if not item.get("address"):
        h1 = soup.select_one("h1.property-info-address, h1[data-testid='address']")
        if h1:
            item["address"] = clean_text(h1.get_text(" ", strip=True))

    if not item.get("price"):
        pr = soup.select_one("div.property-price, span[data-testid='listing-details__summary-title']")
        if pr:
            item["price"] = clean_price(pr.get_text(" ", strip=True))

    if not item.get("description"):
        meta = soup.select_one("meta[name='description']") or soup.select_one("meta[property='og:description']")
        if meta and meta.get("content"):
            item["description"] = clean_text(meta["content"])

    if not item.get("image_urls"):
        item["image_urls"] = extract_images_generic(soup)
    item["image_urls"] = filter_photo_urls(item.get("image_urls", []))[:40]

    # Features (tên class hay đổi, nên lượm theo ul/li chung)
    feats = []
    for el in soup.select("ul.property-features li, ul[class*='features'] li"):
        t = clean_text(el.get_text(" ", strip=True))
        if t: feats.append(t)
    if feats: item["features"] = feats[:50]

    # Floorplan
    a = soup.find("a", string=re.compile(r"floor\s*plan", re.I))
    if a and a.get("href"):
        href = a["href"]
        if not href.startswith("http"):
            href = "https://www.realestate.com.au" + href
        item["floorplan_url"] = href

    # Agent - improved extraction
    agent_selectors = [
        "a.realestate-agent__name",
        "[data-testid='agent-name']",
        ".agent-name",
        ".listing-agent",
        ".property-agent",
        "a[href*='agent']"
    ]
    
    for selector in agent_selectors:
        an = soup.select_one(selector)
        if an:
            item["agent_name"] = clean_text(an.get_text(" ", strip=True))
            break
    
    # Agent phone - improved extraction
    phone_selectors = [
        "a.realestate-agent__phone",
        "[data-testid='agent-phone']",
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

    # Inspection times - improved extraction
    times = []
    inspection_selectors = [
        "div.inspection-times time",
        "[data-testid='inspection-times'] time",
        ".inspection-times",
        "[data-testid*='inspection'] time",
        "[data-testid*='inspection']"
    ]
    
    for selector in inspection_selectors:
        for tim in soup.select(selector):
            if tim.get("datetime"):
                times.append(tim["datetime"])
            elif tim.get_text(strip=True):
                text = clean_text(tim.get_text(strip=True))
                if text and ("am" in text.lower() or "pm" in text.lower() or ":" in text):
                    times.append(text)
        if times:
            break
    
    if times: 
        item["inspection_times"] = times[:10]

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

    # Additional property details for RealEstate.com.au
    # Property size/land area
    size_selectors = [
        "[data-testid*='property-size']",
        "[data-testid*='land-area']",
        ".property-size",
        ".land-area",
        ".property-details .size",
        ".property-info .size"
    ]
    
    for selector in size_selectors:
        size_el = soup.select_one(selector)
        if size_el:
            size_text = clean_text(size_el.get_text(strip=True))
            if size_text and ("m²" in size_text or "sqm" in size_text.lower()):
                item["property_size"] = size_text
                break
    
    # Property status
    status_selectors = [
        "[data-testid*='listing-status']",
        "[data-testid*='property-status']",
        ".listing-status",
        ".property-status",
        ".status-badge",
        ".property-badge"
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
        ".estimated-price",
        ".auction-price"
    ]
    
    for selector in price_guide_selectors:
        price_el = soup.select_one(selector)
        if price_el:
            price_text = clean_text(price_el.get_text(strip=True))
            if price_text and ("guide" in price_text.lower() or "range" in price_text.lower() or "auction" in price_text.lower()):
                item["price_guide"] = price_text
                break
    
    # Agency information
    agency_selectors = [
        "[data-testid*='agency']",
        "[data-testid*='real-estate']",
        ".agency-name",
        ".real-estate-agency",
        ".listing-agency",
        ".property-agency"
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
        r'id["\']?\s*[:=]\s*["\']?(\d{8,})',
        r'/property-(\d+)/'
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
        ".dom",
        ".property-dom"
    ]
    
    for selector in dom_selectors:
        dom_el = soup.select_one(selector)
        if dom_el:
            dom_text = clean_text(dom_el.get_text(strip=True))
            if dom_text and ("day" in dom_text.lower() or "dom" in dom_text.lower()):
                item["days_on_market"] = dom_text
                break

    return item
