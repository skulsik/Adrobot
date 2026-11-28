from pydantic import BaseModel, ConfigDict, Field


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    alias: str | None = Field(default=None, max_length=255)
    geo_code: str = Field(min_length=2, max_length=3)
    offer_id: int = Field(gt=0)
    domain_id: int = Field(gt=0)
    group_id: int = Field(gt=0)
    traffic_source_id: int = Field(gt=0)


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    alias: str | None = Field(default=None, max_length=255)
    domain_id: int | None = Field(default=None, gt=0)
    group_id: int | None = Field(default=None, gt=0)
    traffic_source_id: int | None = Field(default=None, gt=0)


class CampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    keitaro_id: int
    name: str
    alias: str | None
    state: str | None
    domain_id: int | None
    group_id: int | None
    traffic_source_id: int | None
    is_present_in_keitaro: bool


class CampaignListResponse(BaseModel):
    items: list[CampaignResponse]
    total: int
    offset: int
    limit: int


class CampaignCreateResponse(BaseModel):
    status: str
    campaign: CampaignResponse
    streams: dict
    message: str
