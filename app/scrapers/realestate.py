# app/scrapers/realestate.py
import logging, re
from bs4 import BeautifulSoup
from .utils import fetch_url, clean_text, clean_price, jsonld_blocks, extract_number

logger = logging.getLogger(__name__)

def _from_jsonld(blocks: list[dict]) -> dict | None:
    # Realestate thường có "Product", "Offer", "SingleFamilyResidence"... với image & offers
    best = {}
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

            bed = (b.get("numberOfRooms") or b.get("numberOfBedrooms") or
                   b.get("itemOffered", {}).get("numberOfBedrooms"))
            bath = (b.get("numberOfBathroomsTotal") or b.get("numberOfBathrooms") or
                    b.get("itemOffered", {}).get("numberOfBathroomsTotal"))
            car  = b.get("numberOfParkingSpaces") or b.get("itemOffered", {}).get("numberOfParkingSpaces")

            desc = b.get("description") or ""
            ptype = b.get("@type") or b.get("itemOffered", {}).get("@type")

            # Chỉ nhận nếu có Address hoặc có Images hợp lệ
            if address or images:
                best = {
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
    return best or None

def _images_fallback(soup: BeautifulSoup) -> list[str]:
    out = []
    for img in soup.select('img[src]'):
        src = img.get("src")
        if src and src.startswith("http"):
            out.append(src.split("?")[0])
    return list(dict.fromkeys(out))[:20]

def scrape_realestate(url: str) -> dict | None:
    soup = fetch_url(url)
    if not soup:
        return None

    try:
        data = {
            "source": "realestate.com.au",
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

        jl = _from_jsonld(jsonld_blocks(soup))
        if jl:
            data.update(jl)

        # Fallback HTML
        addr = soup.select_one("h1.property-info-address")
        if addr: data["address"] = clean_text(addr.text)

        price = soup.select_one("div.property-price")
        if price: data["price"] = clean_price(price.text)

        bed = soup.select_one(".rui-icon-bed + span")
        if bed: data["bedrooms"] = extract_number(bed.text)
        bath = soup.select_one(".rui-icon-bath + span")
        if bath: data["bathrooms"] = extract_number(bath.text)
        car  = soup.select_one(".rui-icon-car + span")
        if car: data["parking"] = extract_number(car.text)

        desc = soup.select_one("div.property-info__description")
        if desc: data["description"] = clean_text(desc.get_text(" ", strip=True))

        feats = []
        for li in soup.select("ul.property-features li"):
            t = clean_text(li.get_text(" ", strip=True))
            if t: feats.append(t)
        data["features"] = feats

        imgs = data["image_urls"] or _images_fallback(soup)
        data["image_urls"] = imgs[:20]

        # floorplan
        for a in soup.find_all("a"):
            txt = clean_text(a.get_text(" ", strip=True)).lower()
            if "floorplan" in txt and a.has_attr("href"):
                data["floorplan"] = a["href"]
                break

        # agent (các class có thể thay đổi, để fallback nhẹ)
        ag = soup.select_one('[class*="agent"] [class*="name"], .realestate-agent__name')
        if ag: data["agent_name"] = clean_text(ag.get_text(" ", strip=True))
        ph = soup.select_one('[class*="agent"] [href^="tel:"], .realestate-agent__phone')
        if ph: data["agent_phone"] = clean_text(ph.get_text(" ", strip=True))

        # inspections
        ins = []
        for t in soup.select("time[datetime]"):
            ins.append(t["datetime"])
        data["inspection_times"] = list(dict.fromkeys(ins))

        return data
    except Exception as e:
        logger.error(f"Realestate scrape error: {e}", exc_info=True)
        return None
