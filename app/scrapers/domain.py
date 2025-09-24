from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
import re
from .utils import (
    fetch_url, clean_text, clean_price, jsonld_blocks,
    to_int_opt, extract_images_generic, filter_photo_urls, first_href
)

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
        ptype = blk.get("propertyType") or blk.get("@type")
        if isinstance(ptype, list):
            item["property_type"] = ", ".join([str(x) for x in ptype])
        elif isinstance(ptype, str):
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
        summary = soup.select_one('div[data-testid="listing-details__summary-title"]')
        if summary:
            item["price"] = clean_price(summary.get_text(" ", strip=True))

    if not item.get("description"):
        meta = soup.select_one("meta[name='description']") or soup.select_one("meta[property='og:description']")
        if meta and meta.get("content"):
            item["description"] = clean_text(meta["content"])

    if not item.get("image_urls"):
        item["image_urls"] = extract_images_generic(soup)
    item["image_urls"] = filter_photo_urls(item.get("image_urls", []))[:40]

    # Features
    feats = []
    for el in soup.select("div[data-testid='listing-details__features'] li"):
        t = clean_text(el.get_text(" ", strip=True))
        if t: feats.append(t)
    if feats: item["features"] = feats[:50]

    # Floorplan
    # Domain thường có link riêng
    fp = soup.select_one("a[data-testid='floorplan-link']")
    if fp and fp.get("href"):
        item["floorplan_url"] = fp["href"]

    # Agent
    an = soup.select_one("a[data-testid='listing-details__agent-name']")
    ap = soup.select_one("a[data-testid='agent-phone']")
    if an: item["agent_name"] = clean_text(an.get_text(" ", strip=True))
    if ap: item["agent_phone"] = clean_text(ap.get_text(" ", strip=True))

    # Inspections
    times = []
    for tim in soup.select("div[data-testid='inspection-times'] time"):
        if tim.get("datetime"):
            times.append(tim["datetime"])
    if times: item["inspection_times"] = times

    return item
