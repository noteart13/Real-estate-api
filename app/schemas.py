# app/schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional

class PropertyBase(BaseModel):
    source: str
    url: Optional[str] = None
    address: str
    price: str
    bedrooms: Optional[str] = Field("N/A")
    bathrooms: Optional[str] = Field("N/A")
    parking: Optional[str] = Field("N/A")
    property_type: Optional[str] = Field("N/A")
    description: Optional[str] = Field("N/A")
    features: List[str] = Field(default_factory=list)
    image_urls: List[str] = Field(default_factory=list)
    floorplan: Optional[str] = Field(None)
    agent_name: Optional[str] = Field("N/A")
    agent_phone: Optional[str] = Field("N/A")
    inspection_times: List[str] = Field(default_factory=list)

class PropertyResponse(PropertyBase):
    image_embeddings: List[List[float]] = Field(default_factory=list)

class SearchResponse(BaseModel):
    properties: List[PropertyResponse]
