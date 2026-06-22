from __future__ import annotations
from functools import lru_cache
from typing import Optional, List
from pydantic import field_validator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _empty_to_none(v):
    if v == "" or v is None:
        return None
    return v


def parse_ids(v) -> List[int]:
    if v is None or v == "":
        return []
    if isinstance(v, list):
        return [int(x) for x in v]
    return [int(x.strip()) for x in str(v).split(",") if x.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    database_url: str
    admin_ids_csv: str = Field(default="", validation_alias="ADMIN_IDS")
    trusted_ids_csv: str = Field(default="", validation_alias="TRUSTED_IDS")

    main_group_id: Optional[int] = None
    pass_soiree_group_id: Optional[int] = None
    pass_total_group_id: Optional[int] = None
    vip_javana_group_id: Optional[int] = None
    log_group_id: Optional[int] = None
    public_bot_username: Optional[str] = None

    default_vote_goal: int = 120
    default_time_slot: str = "22:30-00:45"
    auto_schedule_enabled: bool = True
    timezone: str = "Europe/Paris"
    paypal_text: Optional[str] = None
    revolut_text: Optional[str] = None
    crypto_text: Optional[str] = None
    railway_environment: str = "production"

    @field_validator("main_group_id", "pass_soiree_group_id", "pass_total_group_id", "vip_javana_group_id", "log_group_id", mode="before")
    @classmethod
    def _optional_int(cls, v):
        return _empty_to_none(v)

    @property
    def admin_ids(self) -> List[int]:
        return parse_ids(self.admin_ids_csv)

    @property
    def trusted_ids(self) -> List[int]:
        return parse_ids(self.trusted_ids_csv)

    @property
    def all_trusted(self) -> set[int]:
        return set(self.admin_ids) | set(self.trusted_ids)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
