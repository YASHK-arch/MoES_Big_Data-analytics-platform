"""ReliefCenter model for disaster emergency shelters and hospitals."""

import uuid
from datetime import datetime, timezone

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class ReliefCenter(Base):
    """Authoritative emergency relief shelter or medical center entity."""

    __tablename__ = "relief_centers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    center_type = Column(String(50), nullable=False, default="SHELTER")  # SHELTER, HOSPITAL, RELIEF_CAMP
    address = Column(Text, nullable=True)
    district_name = Column(String(100), nullable=True, index=True)
    state_name = Column(String(100), nullable=True, index=True)

    capacity = Column(Integer, nullable=False, default=100)
    occupied_count = Column(Integer, nullable=False, default=0)
    contact_phone = Column(String(50), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    # PostGIS geometry point (SRID 4326)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    geom = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
