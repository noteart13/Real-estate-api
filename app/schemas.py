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

class SearchRequest(BaseModel):
    address: str
    include_embeddings: bool = True
    max_images: int = 12

class SearchResponse(BaseModel):
    properties: List[Property]
