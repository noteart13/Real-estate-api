from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
import re
from .utils import (
    fetch_url, clean_text, clean_price, jsonld_blocks,
    to_int_opt, extract_images_generic, filter_photo_urls
)

async def scrape_realestate(url: str) -> Optional[Dict[str, Any]]:
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

        ptype = blk.get("propertyType") or blk.get("@type")
        if isinstance(ptype, list):
            item["property_type"] = ", ".join([str(x) for x in ptype])
        elif isinstance(ptype, str):
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

    # Agent
    an = soup.select_one("a.realestate-agent__name, [data-testid='agent-name']")
    ap = soup.select_one("a.realestate-agent__phone, [data-testid='agent-phone']")
    if an: item["agent_name"] = clean_text(an.get_text(" ", strip=True))
    if ap: item["agent_phone"] = clean_text(ap.get_text(" ", strip=True))

    # Inspection times
    times = []
    for tim in soup.select("div.inspection-times time, [data-testid='inspection-times'] time"):
        if tim.get("datetime"):
            times.append(tim["datetime"])
    if times: item["inspection_times"] = times

    return item
