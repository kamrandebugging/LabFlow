# LabFlow Test Suite & Developer Guide (Doc 09 §9)

This documentation provides the definitive guide for running, authoring, and maintaining automated tests across LabFlow.

---

## 1. How to Run the Test Suite

### Locally
Ensure Docker Compose services (`labflow-postgres` and `labflow-redis`) are running:
```bash
# Start infrastructure containers
make up

# Run full backend test suite
make test

# Or run pytest directly from backend/
cd backend
python -m pytest -v
```

### Running Specific Test Suites
```bash
# Smoke tests (Postgres & Redis live connectivity)
pytest -m smoke -v

# Tenancy isolation fixtures
pytest tests/test_tenant_isolation.py -v

# Factory Boy tests
pytest tests/test_factories.py -v -m factory

# Cross-tenant model registry generator
pytest tests/isolation/ -v -m isolation

# Doc 09 Development Guidelines skeleton scenarios
pytest tests/dg/ -v -m dg
```

### In Continuous Integration (CI)
GitHub Actions runs the test suite on every pull request and push to main against real PostgreSQL 16 and Redis 7 service containers. The pipeline sets:
```yaml
DJANGO_SETTINGS_MODULE: config.settings.test
DATABASE_URL: postgres://labflow:labflow_test_password@localhost:5432/labflow_test
REDIS_URL: redis://localhost:6379/1
```

SQLite is strictly banned at all levels per Doc 09 §9.1. Any configuration pointing to SQLite will immediately abort with exit code 1.

---

## 2. Two-Tenant Fixtures (tenant_a & tenant_b)

Per Doc 04 §13.7, multi-tenancy verification requires two real PostgreSQL schemas with interleaved identifiers:

```python
def test_example(tenant_a: TenantFixture, tenant_b: TenantFixture) -> None:
    # Execute within tenant_a's schema
    with schema_context(tenant_a.schema_name):
        # Database operations target tenant_a schema
        pass

    # Execute within tenant_b's schema
    with schema_context(tenant_b.schema_name):
        # Database operations target tenant_b schema
        pass
```

- Each fixture creates a dedicated schema (`tenant_a` / `tenant_b`) in PostgreSQL and cascades `DROP SCHEMA IF EXISTS ... CASCADE` during teardown.
- Zero data leaks between schemas.

---

## 3. Mandatory Model Factories (Doc 09 §9.4)

### The Standing Rule
1. Every new Django model introduced from **LAB-5 onward** must ship with a corresponding factory in `backend/tests/factories/` in the **exact same pull request**.
2. A model without a factory is an automatic review blocker.
3. Factories must be named `<Model>Factory` (e.g. `PatientFactory`, `InvoiceFactory`).

### Factory Base Classes
- **Tenant Models (`TENANT_APPS`)**: Must inherit from `tests.factories.base.TenantModelFactory`.
  - Enforces execution within an active tenant schema.
  - Calling a `TenantModelFactory` inside the `'public'` schema raises a fatal `RuntimeError`.
- **Public Models (`SHARED_APPS`)**: Must inherit from `tests.factories.base.PublicModelFactory`.
  - Enforces execution inside the `'public'` schema context.

```python
# Example: Adding a factory for a tenant model
from tests.factories.base import TenantModelFactory
from apps.patients.models import Patient


class PatientFactory(TenantModelFactory):
    class Meta:
        model = Patient

    full_name = "Test Patient"
```

---

## 4. Cross-Tenant Harness Generator (Doc 04 §13.7)

The generator (`backend/tests/isolation/generator.py`) walks `settings.TENANT_APPS` dynamically at pytest collection time in $O(M)$ time:

- For every registered tenant model, it generates an isolation test creating a record in `tenant_a` and asserting it is strictly invisible in `tenant_b`.
- **Loud Collection Failure**: If any tenant model is missing a `<Model>Factory`, pytest collection will fail loudly naming the exact model.
- **How to Fix Collection Failure**:
  - Do NOT exclude the model.
  - Add the `<Model>Factory` in `backend/tests/factories/` inheriting from `TenantModelFactory`.
- The `EXCLUDED_MODELS` list in `generator.py` is reserved strictly for documented exceptions (formalized in LAB-54).
