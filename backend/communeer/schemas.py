"""Shared Pydantic base for API response models.

Every response model in this project inherits `CamelModel` so Python stays
snake_case internally while the wire format is camelCase (`memberCount`,
`waId`, `lastSyncedAt`, ...) — this is an integration contract with a
separately-built frontend that has hand-written TypeScript types matching
those exact camelCase names.
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
