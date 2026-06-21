from __future__ import annotations
from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_ids(value: str | None) -> set[int]:
    if not value:
        return set()
    return {int(x.strip()) for x in value.split(',') if x.strip()}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    bot_token: str
    database_url: str
    admin_ids: str = ''
    trusted_ids: str = ''
    main_group_id: int | None = None
    pass_soiree_group_id: int | None = None
    pass_total_group_id: int | None = None
    vip_javana_group_id: int | None = None
    log_group_id: int | None = None
    public_bot_username: str = ''
    default_vote_target: int = 120
    timezone: str = 'Europe/Paris'
    node_env: str = 'production'

    @field_validator('main_group_id', 'pass_soiree_group_id', 'pass_total_group_id', 'vip_javana_group_id', 'log_group_id', mode='before')
    @classmethod
    def empty_string_to_none(cls, value):
        if value == '' or value is None:
            return None
        return value

    @property
    def admin_id_set(self) -> set[int]:
        return parse_ids(self.admin_ids)

    @property
    def trusted_id_set(self) -> set[int]:
        return parse_ids(self.trusted_ids) | self.admin_id_set


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
