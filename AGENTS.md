# Code Guide — Clean Architecture & Design Patterns

> **Reusable reference for AI coding assistants and human developers.** This
> document describes the clean architecture layering, mandatory design patterns,
> coding conventions, and workflow for building maintainable applications.
> Apply this guide to any project that follows clean architecture principles.

---

## Architecture Skeleton

The project follows **Clean Architecture** with four layers plus a composition
root. Dependencies flow **inward**. Outer layers know about inner layers; inner
layers know **nothing** about outer layers.

```
┌──────────────────────────────────────────────────────┐
│  presentation/     API routes, CLI commands,           │  ← adapters
│                    UI controllers                      │
│                    Can import: application, domain,    │
│                    infrastructure (ORM for reads)      │
├──────────────────────────────────────────────────────┤
│  startup/          Composition root, DI factories      │  ← wiring
│                    Can import: EVERYTHING              │
├──────────────────────────────────────────────────────┤
│  core/application/ Use cases, DTOs, selectors          │  ← orchestration
│                    Can import: domain ONLY             │
│                    CANNOT import: infrastructure,      │
│                    presentation                        │
├──────────────────────────────────────────────────────┤
│  core/domain/      Entities, interfaces, pure logic    │  ← innermost
│                    Can import: stdlib, typing, abc,    │
│                    dataclasses, domain-appropriate     │
│                    libraries (e.g., numpy, decimal)    │
│                    CANNOT import: anything else        │
├──────────────────────────────────────────────────────┤
│  infrastructure/   ORM tables, repositories, external  │  ← I/O
│                    services, file I/O, network calls   │
│                    Can import: domain (implements      │
│                    interfaces)                         │
│                    CANNOT import: application,         │
│                    presentation                        │
└──────────────────────────────────────────────────────┘
```

### Layer Purposes

| Layer | Purpose | What Goes Here |
|-------|---------|---------------|
| `core/domain/` | Pure business logic — no frameworks | Entities (dataclasses), interfaces (ABCs/Protocols), domain algorithms, validation rules, value objects, domain services |
| `core/application/` | Orchestration — wires domain objects together | Use cases (interactors), DTOs (data transfer objects), selectors/queries, strategies, application-level orchestrators |
| `infrastructure/` | Concrete implementations of domain interfaces | ORM tables, repositories, mappers, API clients, file-system access, message queues, external service adapters |
| `presentation/` | Adapters to the outside world | REST routes, GraphQL resolvers, CLI commands, event handlers, presenters/formatters, request/response models |
| `startup/` | Composition root — wires everything together | DI factory functions, `bootstrap()` / `create_app()` / `create_server()`, configuration loading |

### Key Rule: Domain → Application Boundary

Application use cases depend on **domain interfaces** (ABCs/Protocols), never on
concrete infrastructure classes. This is the most important rule.

```python
# ✅ CORRECT — use case depends on abstract interface
class CreateOrderUseCase:
    def __init__(self, order_repository: OrderRepository, payment_gateway: PaymentGateway):
        ...

# ❌ WRONG — use case depends on concrete implementation
class CreateOrderUseCase:
    def __init__(self, postgres_order_repository: PostgresOrderRepository, ...):
        ...
```

Concrete implementations are wired in via the composition root (the `startup/` layer).

---

## Design Patterns — Must Apply Strictly

These patterns are **mandatory** when applicable. Code that ignores them will be
flagged in review.

### 1. Dependency Injection (Constructor Injection)

All dependencies are passed through the constructor. No service locators, no
singleton imports, no global state.

```python
# ✅ CORRECT
class OrderService:
    def __init__(self, repository: OrderRepository, notifier: Notifier):
        self._repository = repository
        self._notifier = notifier

# ❌ WRONG
class OrderService:
    def __init__(self):
        self._repository = PostgresOrderRepository()  # hardwired concrete class
```

**Exception:** Outer-layer modules (presentation) may use module-level cached
instances for expensive infrastructure (embedders, LLM clients, browser
renderers) when the framework requires per-module state. These instances are
created by the composition root and referenced via lazy initialization helpers.

```python
# ✅ allowed — Streamlit UI importing Playwright renderer via factory
from webdown.startup.service_factory import create_page_renderer
page_renderer = create_page_renderer()  # one-time init at module level
```

This is acceptable because it is confined to the outermost layer.

### 2. Repository Pattern

All database access goes through repository classes that implement domain
interfaces. Repositories take a domain entity, convert to ORM via mappers,
persist, and convert back.

```
Domain Entity  ←→  Mapper  ←→  ORM Model  ←→  Database
```

```python
# Interface (in core/domain/interfaces/)
class OrderRepository(ABC):
    @abstractmethod
    def save(self, db: Session, order: Order) -> None: ...
    @abstractmethod
    def find_by_id(self, db: Session, order_id: str) -> Order | None: ...

# Implementation (in infrastructure/repositories/)
class SqlOrderRepository(OrderRepository):
    def save(self, db: Session, order: Order) -> None:
        orm_order = order_to_orm(order)  # mapper
        db.add(orm_order)
        db.commit()
```

**Read-access exception:** Complex read queries (searches, aggregations,
reporting) may use ORM or raw queries directly in presentation tools. Write
operations MUST use repositories. This is a pragmatic CQRS-lite approach.

### 3. Strategy Pattern

When behavior varies, define an interface and multiple implementations. The
caller selects the strategy; the use case doesn't care which one.

```python
# Interface
class PricingStrategy(ABC):
    @abstractmethod
    def calculate(self, order: Order) -> Decimal: ...

# Implementations
class FlatPricingStrategy(PricingStrategy): ...
class TieredPricingStrategy(PricingStrategy): ...
class DiscountPricingStrategy(PricingStrategy): ...

# Use case — depends only on the interface
class CalculateOrderTotalUseCase:
    def __init__(self, pricing: PricingStrategy):
        self._pricing = pricing
```

### 4. Factory Pattern (Composition Root)

Complex object graphs are assembled in the `startup/` layer using factory
functions. Factories return fully-wired dependencies with all interfaces
satisfied.

```python
# startup/order_factory.py
def create_order_use_case(db: Session) -> CreateOrderUseCase:
    repository = SqlOrderRepository()
    payment_gateway = StripePaymentGateway()
    notifier = EmailNotifier()
    pricing = TieredPricingStrategy()
    return CreateOrderUseCase(repository, payment_gateway, notifier, pricing)
```

**Rule:** Never construct complex objects inline in use cases or tools.
Always delegate to a factory.

### 5. DTO (Data Transfer Object)

Data crossing layer boundaries (use case input/output) uses dedicated DTO
classes — pure dataclasses with no behavior, no ORM, no domain logic.

```python
# core/application/dto/create_order_result.py
@dataclass
class CreateOrderResult:
    order_id: str
    status: str
    total: Decimal
    error: str | None = None
```

**Convention:** Shared DTOs live in `core/application/dto/`.
API-specific request/response models (Pydantic, etc.) live in `presentation/`.

### 6. Observer / Background Processing

Long-running operations are dispatched to a background processor interface.
The use case queues work and returns immediately; the caller polls progress.

```python
# Interface
class BackgroundProcessor(ABC):
    @abstractmethod
    def submit(self, task: Callable, *args, **kwargs) -> str:
        """Submit a task. Returns a job_id for polling."""
        ...

# Concrete
class ThreadPoolBackgroundProcessor(BackgroundProcessor): ...
class CeleryBackgroundProcessor(BackgroundProcessor): ...
```

### 7. Facade / Presenter

Complex multi-step operations (search → filter → sort → format) are wrapped
behind presenter/facade classes that expose a single clean method.

```python
class ReportPresenter:
    """Wraps multi-step report generation into a single method."""

    def present(self, data: ReportData) -> ReportResponse:
        aggregated = self._aggregator.aggregate(data)
        formatted = self._formatter.format(aggregated)
        return ReportResponse(data=formatted)
```

### 8. Chain of Responsibility

When a request must pass through a sequence of handlers until one succeeds,
use Chain of Responsibility. Each handler tries its approach and delegates
to the next if it fails.

```python
# Interface
class Handler(ABC):
    def set_next(self, handler: "Handler") -> "Handler": ...
    @abstractmethod
    def handle(self, request) -> bool: ...
    def try_handle(self, request) -> bool:  # template method
        return self.handle(request) or (self._next and self._next.try_handle(request))

# Concrete handlers
class SelectorHandler(Handler): ...
class OverlayHandler(Handler): ...
class ScrollHandler(Handler): ...

# Usage — build chain, try once
chain = ScrollHandler()
chain.set_next(SelectorHandler()).set_next(OverlayHandler())
chain.try_handle(page)
```

**When to use:** sequential fallback processing (cookie consent handlers,
request validators, format detectors).

### 9. Template Method

When a process has a fixed skeleton but individual steps vary, define the
skeleton in a base class and let subclasses override the steps.

```python
class PageProcessor:
    def process(self, page, url: str) -> str:
        self._navigate(page, url)
        self._handle_consent(page, url)
        self._scroll_to_load(page)
        return self._extract(page)

    @abstractmethod
    def _handle_consent(self, page, url) -> None: ...
```

**When to use:** multi-step processes where the overall flow is stable but
individual steps need different implementations (page rendering, data ingestion pipelines).

### 10. Pipeline / Extract Method

When a single function grows beyond its responsibility, extract each step
into a named private function. The original becomes a clean dispatcher.

```python
# ❌ god function — 500 lines
def extract_markdown(content, url) -> str: ...

# ✅ pipeline — each step one responsibility
def extract_markdown(content, url) -> str:
    soup = _parse(content)
    _process_headings(soup, output)
    _process_tables(soup, output)
    _process_code_blocks(soup, output)
    ...
```

**When to use:** any function exceeding ~50 lines. The dispatcher itself
should stay under ~30 lines.

### Patterns to AVOID

| Anti-pattern | Why it's banned |
|-------------|-----------------|
| **Singleton** (global state) | Makes testing impossible, violates DI. Use factory + caching if needed. |
| **Service Locator** | Hides dependencies, makes code untestable. Use constructor injection. |
| **God Class** | Single class doing too many things. Split by responsibility. |
| **God Method** | Single function exceeding ~50 lines. Extract into private step methods (see Pipeline pattern). |
| **Anemic Domain Model** | Entities with only getters/setters, logic in services. Put domain logic in entities or domain services. |
| **Inheritance for code reuse** | Prefer composition. Interfaces use ABC/Protocol, not deep class hierarchies. |

### Pattern Decision Guide

| Problem | Pattern |
|---------|---------|
| Swappable behavior at runtime | Strategy |
| Database access behind an interface | Repository |
| Complex object construction | Factory (in startup) |
| Data crossing layer boundaries | DTO |
| Long-running background work | Observer / BackgroundProcessor |
| Complex response formatting | Presenter / Facade |
| Sequential fallback (try A, then B, then C) | Chain of Responsibility |
| Fixed process skeleton, varying steps | Template Method |
| Function exceeding ~50 lines | Pipeline / Extract Method |
| Multiple parsing/conversion strategies | Strategy |

### Size Constraints

| Element | Maximum | Rationale |
|---------|---------|-----------|
| Method / function | ~50 lines | Beyond this, extract step methods (see Pipeline pattern) |
| Class | ~150 lines | Beyond this, split responsibilities |
| File | ~500 lines | Infrastructure services may exceed due to many small functions; review at 500 |

---

## One Class Per File — Strict Rule

Every class, interface (ABC/Protocol), DTO, entity, enum, and strategy lives in
its own file. No exceptions.

**File naming:** `snake_case.py` matching the class name.

```python
# ✅ CORRECT
core/domain/interfaces/order_repository.py    → class OrderRepository(ABC)
core/domain/entities/order.py                 → class Order (dataclass)
core/application/dto/create_order_result.py   → class CreateOrderResult
core/application/use_cases/create_order.py    → class CreateOrderUseCase
infrastructure/repositories/sql_order_repo.py → class SqlOrderRepository

# ❌ WRONG — multiple classes in one file
core/domain/interfaces/repositories.py
    → class OrderRepository, class UserRepository, class ProductRepository  # NO
```

**Exceptions to this rule:**
- `__init__.py` files (package declarations, re-exports)
- File-level helper functions tightly coupled to the single class in the file
- Protocol helper types used only by the one class in the file

---

## Coding Conventions

### Imports

```python
# 1. Standard library
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol

# 2. Third-party
from sqlalchemy.orm import Session
import numpy as np

# 3. Internal — always absolute imports from the project root
from project.core.domain.entities.order import Order as DomainOrder
from project.infrastructure.tables.order import Order as OrmOrder

# Domain entity vs ORM model disambiguation:
#   DomainOrder / OrmOrder  (preferred)
# Never import ORM models as bare names — always alias.
```

### Naming

| Thing | Convention | Example |
|-------|-----------|---------|
| Classes | PascalCase | `CreateOrderUseCase` |
| Interfaces (ABC) | PascalCase, no `I` prefix | `OrderRepository`, `PaymentGateway` |
| Protocols | PascalCase | `Embeddable`, `HasId` |
| Functions/Methods | snake_case | `find_by_customer_id()` |
| Variables | snake_case | `items_shipped` |
| Constants | UPPER_SNAKE | `MAX_RETRY_COUNT` |
| Private members | `_prefix` | `self._repository` |
| File names | snake_case | `create_order.py` |

### Type Hints

All public methods and functions MUST have type hints. Use `| None` not `Optional`.

```python
def execute(self, db: Session, order_id: str) -> CreateOrderResult:
    ...

def find_by_id(self, db: Session, order_id: str) -> Order | None:
    ...
```

### Docstrings

All public classes and methods have docstrings. Format: triple-quote on its own
line, first line is a summary, blank line, then details.

```python
class CreateOrderUseCase:
    """Creates a new order: validates inventory, reserves items, processes
    payment, and sends a confirmation notification."""

    def execute(self, db: Session, request: CreateOrderRequest) -> CreateOrderResult:
        """Execute the create order operation.

        Args:
            db: Database session.
            request: The order creation request DTO.

        Returns:
            CreateOrderResult with the new order ID and status.

        Raises:
            InsufficientInventoryError: If any item is out of stock.
            PaymentFailedError: If payment processing fails.
        """
```

### Domain Entity vs ORM Model

Domain entities are dataclasses in `core/domain/entities/`. ORM models are
database-mapped classes in `infrastructure/tables/`. They are NEVER the same
class. Conversion happens in mapper functions in `infrastructure/repositories/`.

```python
# Domain entity — pure Python, no ORM
@dataclass
class Order:
    id: int | None = None
    order_id: str = ""
    customer_name: str = ""
    total: Decimal = Decimal("0.00")
    ...

# ORM model — database table mapping
class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    order_id = Column(String, unique=True)
    customer_name = Column(String)
    total = Column(Numeric(10, 2))
    ...
```

---

## How to Add a Feature

Follow this sequence when adding new functionality:

### 1. Define the domain interface (if new capability)

```
core/domain/interfaces/my_new_thing.py
  → class MyNewThing(ABC):
        @abstractmethod
        def do_something(self, ...) -> ...: ...
```

### 2. Define domain entities (if new data)

```
core/domain/entities/my_entity.py
  → @dataclass class MyEntity: ...
```

### 3. Define DTOs (if data crosses boundaries)

```
core/application/dto/my_result.py
  → @dataclass class MyResult: ...
```

### 4. Define the use case

```
core/application/use_cases/my_use_case.py
  → class MyUseCase:  # depends on domain interfaces only
```

### 5. Implement the infrastructure

```
infrastructure/tables/my_entity.py            # ORM/database table
infrastructure/repositories/mappers.py        # Add mapper functions
infrastructure/repositories/sql_my_repo.py    # Repository implementation
infrastructure/services/my_thing.py           # Concrete service implementation
```

### 6. Wire it up (composition root)

```
startup/my_factory.py
  → def create_my_use_case() -> MyUseCase: ...
```

### 7. Expose it (presentation)

```
presentation/routes/my_route.py        # REST/API endpoint
presentation/cli/my_command.py         # CLI command
presentation/handlers/my_handler.py    # Event/message handler
```

### 8. Register it

```
presentation/routes/__init__.py    # Register route in the router
startup/api.py or startup/cli.py   # Wire into application entry point
```

---

## Linting & Formatting

This guide recommends **ruff** for linting and **black** for formatting.

```bash
# Format
black src/ tests/

# Lint + auto-fix
ruff check src/ tests/ --fix

# Lint only (no changes)
ruff check src/ tests/
```

**Rules:**
- All code must pass `ruff check` with zero errors before commit.
- All code must be formatted with `black` (line length 88, default).
- CI should reject code that fails either tool.
- Run both from the project root.

---

## Testing

Tests mirror the source structure under a `tests/` directory:

```
tests/
├── test_domain/          # Pure unit tests
├── test_application/     # Use case tests
├── test_infrastructure/  # Integration tests
└── test_presentation/    # End-to-end / API tests
```

- **Domain tests:** Pure unit tests, no database, no filesystem, no network.
  Mock interfaces.
- **Application tests:** Use case tests with mocked infrastructure interfaces.
- **Infrastructure tests:** Integration tests with real databases (in-memory),
  temporary files, or embedded services.
- **Presentation tests:** Full stack tests — create app, send requests, verify
  responses.

Run with: `pytest tests/`

---

## Quick Reference: Dependency Rules

```
┌─────────────────────────────────────────────┐
│            ALLOWED IMPORT RULES              │
├──────────────────┬──────────────────────────┤
│ Layer            │ May Import From           │
├──────────────────┼──────────────────────────┤
│ startup/         │ EVERYTHING                │
│ presentation/    │ application, domain,      │
│                  │ infrastructure (reads)    │
│ core/application/│ domain ONLY               │
│ core/domain/     │ stdlib, typing,           │
│                  │ domain-appropriate libs   │
│ infrastructure/  │ domain (implements)       │
└──────────────────┴──────────────────────────┘
```

**Golden rule:** The arrow of dependency always points inward. The domain
layer never knows about databases, frameworks, or network protocols.
