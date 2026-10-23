# LabFlow Test Suite & Factory Guidelines

## Standing Rule: Model Factories (Doc 09 §9.4)

1. **Mandatory Model Factories**:
   Every new Django model added to LabFlow from **LAB-5 onward** must ship with a corresponding `factory_boy` factory in `backend/tests/factories/` in the **exact same pull request** as the model.
2. **Naming Convention**:
   Factories must strictly follow the `<Model>Factory` naming convention (e.g. `PatientFactory`, `InvoiceFactory`, `SampleFactory`).
3. **Inheritance & Schema Isolation**:
   - Models residing in tenant schemas (`TENANT_APPS`) **must inherit from `TenantModelFactory`** (`tests.factories.base.TenantModelFactory`).
   - Models residing in the public schema (`SHARED_APPS`) **must inherit from `PublicModelFactory`** (`tests.factories.base.PublicModelFactory`).
   - Any attempt to instantiate a tenant model factory while in the `public` schema will raise a fatal `RuntimeError`.
4. **Review Blocker**:
   Any pull request that introduces a model without its corresponding `<Model>Factory` is an **automatic review blocker**. Hand-built model instances in individual tests are strictly banned to prevent test fixtures from drifting out of sync with Doc 02 database schema constraints.
5. **No Speculative Factories**:
   Do not create factories for models that do not exist yet in the codebase.
