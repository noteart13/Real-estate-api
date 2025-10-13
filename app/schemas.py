from pydantic import BaseModel, Field
from typing import List, Optional

class Property(BaseModel):
    source: str                            # "domain" | "realestate"
    url: Optional[str] = None
    address: Optional[str] = None
    price: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    parking: Optional[int] = None
    property_type: Optional[str] = None
    description: Optional[str] = None
    features: List[str] = Field(default_factory=list)
    image_urls: List[str] = Field(default_factory=list)
    floorplan_url: Optional[str] = None
    agent_name: Optional[str] = None
    agent_phone: Optional[str] = None
    inspection_times: List[str] = Field(default_factory=list)
    image_embeddings: List[List[float]] = Field(default_factory=list)
    
    # Additional fields for enhanced data
    property_size: Optional[str] = None      # e.g., "668m²"
    listing_status: Optional[str] = None     # e.g., "FOR SALE NOW", "Under Contract"
    price_guide: Optional[str] = None         # e.g., "Price guide", "Auction"
    agency_name: Optional[str] = None         # Real estate agency name
    listing_id: Optional[str] = None          # Property listing ID
    days_on_market: Optional[str] = None       # Days on market

class SearchRequest(BaseModel):
    address: str
    include_embeddings: bool = True
    max_images: int = 12
    # Matching controls
    strict_match: bool = False           # require strict address match when true
    allow_near: bool = True              # when no strict match, allow near matches

class SearchResponse(BaseModel):
    properties: List[Property]
