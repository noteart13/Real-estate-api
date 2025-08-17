# app/scrapers/domain.py
import logging, re
from bs4 import BeautifulSoup
from .utils import fetch_url, clean_text, clean_price, jsonld_blocks, extract_number

logger = logging.getLogger(__name__)

def _from_jsonld(blocks: list[dict]) -> dict | None:
    # Tìm block @type Property / Residence / Product có address & image
    for b in blocks:
        try:
            addr = b.get("address") or b.get("itemOffered", {}).get("address")
            if isinstance(addr, dict):
                address = clean_text(" ".join(filter(None, [
                    addr.get("streetAddress"), addr.get("addressLocality"),
                    addr.get("addressRegion"), addr.get("postalCode"), addr.get("addressCountry")
                ])))
            else:
                address = clean_text(str(addr))

            offers = b.get("offers") or {}
            price = offers.get("price") or offers.get("priceSpecification", {}).get("price")

            images = b.get("image") or []
            if isinstance(images, str): images = [images]

            bed = b.get("numberOfRooms") or b.get("numberOfBedrooms")
            bath = b.get("numberOfBathroomsTotal") or b.get("numberOfBathrooms")
            car  = b.get("numberOfParkingSpaces") or b.get("numberOfParkingSpace")

            desc = b.get("description") or ""
            ptype = b.get("@type") or b.get("itemOffered", {}).get("@type")

            if address:
                return {
                    "address": address or "N/A",
                    "price": clean_price(str(price) if price else ""),
                    "bedrooms": extract_number(str(bed)) if bed else "N/A",
                    "bathrooms": extract_number(str(bath)) if bath else "N/A",
                    "parking": extract_number(str(car)) if car else "N/A",
                    "property_type": clean_text(ptype) if ptype else "Property",
                    "description": clean_text(desc) or "N/A",
                    "image_urls": [i for i in images if isinstance(i, str)],
                }
        except Exception:
            continue
    return None

def _images_fallback(soup: BeautifulSoup) -> list[str]:
    out = []
    for img in soup.select('img[src]'):
        src = img.get("src")
        if src and src.startswith("http"):
            out.append(src.split("?")[0])
    return list(dict.fromkeys(out))[:20]

def scrape_domain(url: str) -> dict | None:
    soup = fetch_url(url)
    if not soup:
        return None
    try:
        data = {
            "source": "domain.com.au",
            "url": url,
            "address": "N/A",
            "price": "Contact agent",
            "bedrooms": "N/A",
            "bathrooms": "N/A",
            "parking": "N/A",
            "property_type": "Property",
            "description": "N/A",
            "features": [],
            "image_urls": [],
            "floorplan": None,
            "agent_name": "N/A",
            "agent_phone": "N/A",
            "inspection_times": [],
        }

        # 1) JSON-LD trước
        jl = _from_jsonld(jsonld_blocks(soup))
        if jl:
            data.update(jl)

        # 2) Fallback HTML selectors
        addr = soup.select_one('h1[data-testid="address"]')
        if addr: data["address"] = clean_text(addr.text)
        price = soup.select_one('[data-testid="price"]')
        if price: data["price"] = clean_price(price.text)

        feats = soup.select('[data-testid="property-features"] > div')
        if feats:
            if len(feats) > 0: data["bedrooms"]  = extract_number(feats[0].get_text(" ", strip=True))
            if len(feats) > 1: data["bathrooms"] = extract_number(feats[1].get_text(" ", strip=True))
            if len(feats) > 2: data["parking"]   = extract_number(feats[2].get_text(" ", strip=True))

        desc = soup.select_one('[data-testid="listing-details__description"]')
        if desc: data["description"] = clean_text(desc.get_text(" ", strip=True))

        ft_list = []
        for li in soup.select('div[data-testid="listing-details__features"] li'):
            t = clean_text(li.get_text(" ", strip=True))
            if t: ft_list.append(t)
        data["features"] = ft_list

        imgs = data["image_urls"] or []
        if not imgs:
            imgs = _images_fallback(soup)
        data["image_urls"] = imgs[:20]

        # floorplan
        fp = soup.select_one('a[data-testid="floorplan-link"]')
        if fp and fp.has_attr("href"):
            data["floorplan"] = fp["href"]

        # agent
        ag = soup.select_one('a[data-testid="listing-details__agent-name"]')
        if ag: data["agent_name"] = clean_text(ag.get_text(" ", strip=True))
        ph = soup.select_one('a[data-testid="agent-phone"]')
        if ph: data["agent_phone"] = clean_text(ph.get_text(" ", strip=True))

        # inspections
        ins = []
        for t in soup.select('div[data-testid="inspection-times"] time'):
            if t.has_attr("datetime"):
                ins.append(t["datetime"])
        data["inspection_times"] = ins

        return data
    except Exception as e:
        logger.error(f"Domain scrape error: {e}", exc_info=True)
        return None
