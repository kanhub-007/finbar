"""SQLAlchemy ORM table for indicator artifacts."""

from sqlalchemy import Column, Integer, String, Text

from finbar.infrastructure.data.connection import Base


class IndicatorArtifact(Base):
    """Persisted indicator job artifact — bars + metadata."""

    __tablename__ = "indicator_artifacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, unique=True, nullable=False, index=True)
    symbol = Column(String, nullable=False)
    source = Column(String, nullable=False)
    interval = Column(String, nullable=False)
    mode = Column(String, nullable=False)
    timeframe_alias = Column(String, nullable=False, default="primary")
    status = Column(String, nullable=False, default="completed")
    bars_json = Column(Text, nullable=False)
    total_bar_count = Column(Integer, nullable=False, default=0)
    indicators_applied_json = Column(Text, default="[]")
    features_applied_json = Column(Text, default="[]")
    content_hash = Column(String, default="")
    created_at = Column(String, nullable=False)
