# Sandbox test shims — NOT production code

Minimal stand-ins for fastapi / pydantic / slowapi so backend unit tests run
in environments without PyPI access (the Claude sandbox). Real packages always
take precedence: only add this directory to PYTHONPATH explicitly, e.g.

    PYTHONPATH=backend/tests/shims python3 <runner>

Never install or import these in production. Route decorators are no-ops;
the pydantic shim only supports defaults + List[Model] coercion.
