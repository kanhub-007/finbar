"""Symbol API endpoints — metadata, list cached symbols, sources."""

from fastapi import APIRouter, HTTPException, Query

from finbar.presentation.api.dto.responses import (
    SymbolInfoResponse,
)
from finbar.presentation.mcp.tools._shared import (
    _get_db,
    _make_get_symbol_info_use_case,
    _make_list_cached_use_case,
)

router = APIRouter(prefix="/api/symbols", tags=["Symbols"])


@router.get(
    "/{symbol}",
    response_model=SymbolInfoResponse,
    summary="Get symbol metadata",
)
def get_symbol(symbol: str):
    """Retrieve company/asset metadata for a ticker symbol."""
    db = _get_db()
    try:
        use_case = _make_get_symbol_info_use_case(db)
        info = use_case.execute(symbol.upper())
        if info is None:
            raise HTTPException(status_code=404, detail=f"Symbol not found: {symbol}")
        return SymbolInfoResponse(
            symbol=info.symbol,
            company_name=info.company_name,
            sector=info.sector,
            industry=info.industry,
            exchange=info.exchange,
            market_cap=info.market_cap,
        )
    finally:
        db.close()


@router.get(
    "/cached",
    response_model=list[str],
    summary="List cached symbols",
)
def list_cached(source: str | None = Query(None, description="Data source filter")):
    """List symbols that have data in the local cache."""
    db = _get_db()
    try:
        use_case = _make_list_cached_use_case(db)
        return use_case.execute(source=source)
    finally:
        db.close()
