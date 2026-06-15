"""SQLAlchemy ORM table for indicator artifacts."""

from sqlalchemy import Column, Index, Integer, String, Text

from finbar.infrastructure.data.connection import Base


class IndicatorArtifact(Base):
    """Persisted indicator job artifact — bars + metadata.

    Metadata columns (``columns_json``, ``start_date``, ``end_date``)
    are populated at save time so listing/describe operations avoid
    deserialising the full ``bars_json`` blob.
    """

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
    # Pre-computed metadata so list/describe never parse bars_json.
    columns_json = Column(Text, default="[]")
    start_date = Column(String, default="", index=True)
    end_date = Column(String, default="")
    content_hash = Column(String, default="", index=True)
    created_at = Column(String, nullable=False)

    __table_args__ = (
        # Supports list_metadata() filters on (symbol, source, interval)
        # without a full table scan.
        Index(
            "ix_indicator_artifacts_symbol_source_interval",
            "symbol",
            "source",
            "interval",
        ),
    )
