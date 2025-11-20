# MT5 Python Bot - Agent Guidelines

## Build/Test Commands
- **Install dependencies**: `pip install -r requirements.txt`
- **Run tests**: `python -m pytest tests/`
- **Run single test**: `python -m pytest tests/test_bot.py::test_healthcheck`
- **Run live bot**: `python main.py`

## Code Style Guidelines

### Formatting & Imports
- Use 4-space indentation (configured in .editorconfig)
- LF line endings, UTF-8 encoding
- Import order: standard library → third-party → local imports
- Use `from __future__ import annotations` for forward references
- Type hints required for all function parameters and return values

### Naming Conventions
- Classes: PascalCase (e.g., `SymbolMeta`, `Candle`)
- Functions/variables: snake_case (e.g., `init_mt5`, `account_user`)
- Constants: UPPER_SNAKE_CASE (e.g., `SYMBOL`, `TIMEFRAME`)
- Private members: underscore prefix (e.g., `_calculate_position_size`)

### Architecture Patterns
- Use Pydantic for configuration and data validation
- Domain models in `app/domain/` use `@dataclass(frozen=True)`
- Services in `app/services/` handle business logic
- Adapters in `app/adapters/` interface with external systems
- Infrastructure in `app/infra/` for cross-cutting concerns

### Error Handling
- Use descriptive error messages with context
- Raise `RuntimeError` for MT5 connection failures
- Use `pytest.raises` for testing exception cases
- Log errors appropriately using the logging infrastructure

### Testing
- Use pytest with unittest.mock for external dependencies
- Test both success and failure paths
- Mock MT5 calls in all tests
- Follow AAA pattern (Arrange, Act, Assert)
