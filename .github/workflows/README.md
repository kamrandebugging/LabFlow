# GitHub Actions CI/CD Workflows

Continuous Integration and Continuous Deployment pipelines for LabFlow.

The production CI pipeline will be implemented in story **LAB-3** per **Doc 09 §12**, executing:
- Linting and formatting checks (`make lint`)
- Backend and frontend test suites (`make test`)
- Migration drift and schema validation
- Playwright E2E smoke tests
