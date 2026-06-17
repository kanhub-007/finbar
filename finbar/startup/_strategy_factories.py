"""Strategy factories — parser, providers, schema, capabilities, signal calc."""

from typing import TYPE_CHECKING

from finbar_strategy_runtime.parser.strategy_capability_service import (
    StrategyCapabilityService,
)
from finbar_strategy_runtime.parser.strategy_definition_parser import (
    StrategyDefinitionParser,
)
from finbar_strategy_runtime.parser.strategy_schema_provider import (
    StrategySchemaProvider,
)
from sqlalchemy.orm import Session

from finbar.core.application.use_cases.delete_strategy_definition import (
    DeleteStrategyDefinitionUseCase,
)
from finbar.core.application.use_cases.explain_strategy_definition import (
    ExplainStrategyDefinitionUseCase,
)
from finbar.core.application.use_cases.save_strategy_definition import (
    SaveStrategyDefinitionUseCase,
)
from finbar.core.application.use_cases.validate_strategy_definition import (
    ValidateStrategyDefinitionUseCase,
)
from finbar.infrastructure.repositories.sql_strategy_document_repository import (
    SqlStrategyDocumentRepository,
)
from finbar.infrastructure.services.builtin_strategy_provider import (
    BuiltinStrategyProvider,
)
from finbar.infrastructure.services.composite_strategy_provider import (
    CompositeStrategyProvider,
)
from finbar.infrastructure.services.database_strategy_provider import (
    DatabaseStrategyProvider,
)
from finbar.infrastructure.services.strategy_definition_factory import (
    StrategyDefinitionFactory,
)

if TYPE_CHECKING:
    from finbar_strategy_runtime.indicators.pandas_signal_calculator import (
        PandasSignalCalculator,
    )

_parser: StrategyDefinitionParser | None = None
_capability_service: StrategyCapabilityService | None = None
_schema_provider: StrategySchemaProvider | None = None
_builtin_strategy_provider: BuiltinStrategyProvider | None = None
_json_strategy_factory: StrategyDefinitionFactory | None = None
_signal_calculator: "PandasSignalCalculator | None" = None


def get_parser() -> StrategyDefinitionParser:
    """Return the shared strategy JSON parser."""
    global _parser
    if _parser is None:
        _parser = StrategyDefinitionParser()
    return _parser


def get_capability_service() -> StrategyCapabilityService:
    """Return the shared strategy capability service."""
    global _capability_service
    if _capability_service is None:
        _capability_service = StrategyCapabilityService()
    return _capability_service


def get_schema_provider() -> StrategySchemaProvider:
    """Return the shared strategy schema provider."""
    global _schema_provider
    if _schema_provider is None:
        _schema_provider = StrategySchemaProvider()
    return _schema_provider


def get_json_strategy_factory() -> StrategyDefinitionFactory:
    """Return the JSON strategy factory."""
    global _json_strategy_factory
    if _json_strategy_factory is None:
        _json_strategy_factory = StrategyDefinitionFactory()
    return _json_strategy_factory


def get_signal_calculator() -> "PandasSignalCalculator":
    """Return the shared signal interpretation calculator."""
    global _signal_calculator
    if _signal_calculator is None:
        from finbar_strategy_runtime.domain.services.confidence_scorer import (
            ConfidenceScorer,
        )
        from finbar_strategy_runtime.indicators.pandas_signal_calculator import (
            PandasSignalCalculator,
        )

        _signal_calculator = PandasSignalCalculator(scorer=ConfidenceScorer())
    return _signal_calculator


def make_strategy_provider(db: Session | None = None) -> CompositeStrategyProvider:
    """Create the composite strategy provider used by backtesting tools."""
    global _builtin_strategy_provider
    if _builtin_strategy_provider is None:
        _builtin_strategy_provider = BuiltinStrategyProvider()

    providers = [_builtin_strategy_provider]
    if db is not None:
        doc_repo = SqlStrategyDocumentRepository(db)
        providers.append(DatabaseStrategyProvider(doc_repo, get_parser()))
    return CompositeStrategyProvider(providers)


def make_save_strategy_definition_use_case(
    db: Session,
) -> SaveStrategyDefinitionUseCase:
    """Create a use case for validating and saving strategy documents."""
    return SaveStrategyDefinitionUseCase(
        SqlStrategyDocumentRepository(db),
        parser=get_parser(),
    )


def make_delete_strategy_definition_use_case(
    db: Session,
) -> DeleteStrategyDefinitionUseCase:
    """Create a use case for deleting strategy documents."""
    return DeleteStrategyDefinitionUseCase(SqlStrategyDocumentRepository(db))


def make_explain_strategy_definition_use_case() -> ExplainStrategyDefinitionUseCase:
    """Create a use case for explaining strategy JSON."""
    return ExplainStrategyDefinitionUseCase(parser=get_parser())


def make_validate_strategy_definition_use_case() -> ValidateStrategyDefinitionUseCase:
    """Create a use case for validating strategy JSON."""
    return ValidateStrategyDefinitionUseCase(get_parser())
