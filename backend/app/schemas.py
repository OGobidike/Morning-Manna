

"""Response and request shapes for the API (what JSON goes in and out)."""

from pydantic import BaseModel, ConfigDict


class PlanOut(BaseModel):
    """One reading plan, as the app sees it."""

    # Allow building this schema straight from a SQLAlchemy row
    model_config = ConfigDict(from_attributes=True)

    # Three fields id, name, and description, all required
    id: int
    name: str
    description: str
