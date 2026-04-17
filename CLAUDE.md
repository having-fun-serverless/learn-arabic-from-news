## Before Any Work

Run `uv run task check` after every change (lint + test + validate + build).

## Key Commands

| Command | What it does |
|---|---|
| `uv run task check` | lint + test + sam validate + sam build |
| `uv run task format` | auto-fix ruff |
| `uv run task deploy` | deploy to AWS |

## Stack

- Python 3.12, ARM64 · AWS SAM · Lambda Powertools · uv · ruff · pytest + moto

## Structure

- `lambdas/` — Lambda function code (one dir per function)
- `tests/` — pytest unit tests (moto for AWS mocking)
- `template.yaml` — SAM infrastructure
