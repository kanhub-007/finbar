"""QueryArtifactBarsUseCase — page and filter stored artifact bars."""

from finbar.core.application.dto.query_artifact_bars_result import (
    QueryArtifactBarsResult,
)
from finbar.core.domain.interfaces.indicator_artifact_provider import (
    IndicatorArtifactProvider,
)


class QueryArtifactBarsUseCase:
    """Query stored artifact bars with pagination and column filters."""

    def __init__(self, provider: IndicatorArtifactProvider):
        """Create the use case with an artifact provider."""
        self._provider = provider

    def execute(
        self,
        artifact_id: str,
        columns: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 0,
        page_size: int = 500,
    ) -> QueryArtifactBarsResult:
        """Return one page of filtered artifact bars."""
        try:
            bars, page, page_size, total_pages, total_count, returned_columns = (
                self._provider.query_artifact_bars(
                    artifact_id,
                    columns,
                    start_date,
                    end_date,
                    page,
                    page_size,
                )
            )
        except KeyError:
            return QueryArtifactBarsResult(found=False, artifact_id=artifact_id)
        except Exception as exc:
            return QueryArtifactBarsResult(
                found=False,
                artifact_id=artifact_id,
                error=str(exc),
            )
        return QueryArtifactBarsResult(
            found=True,
            artifact_id=artifact_id,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            total_bar_count=total_count,
            bar_count=len(bars),
            columns=returned_columns,
            bars=bars,
        )
