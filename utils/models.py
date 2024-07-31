import time
from typing import List, Optional, Literal

from pydantic import BaseModel, Field


class RecommendationsResponse(BaseModel):
    item_ids: List[str] = Field([], description="list of recommended items")


class InteractEvent(BaseModel):
    user_id: str = Field(description="identifier of user")
    item_ids: List[str] = Field(description="identifiers of interacted items")
    actions: List[Literal['like', 'dislike']] = Field(description="positive or negative reaction for items")
    timestamp: Optional[float] = Field(time.time(), description="timestamp of event")


class NewItemsEvent(BaseModel):
    item_ids: List[str] = Field(description="identifiers of new items")
