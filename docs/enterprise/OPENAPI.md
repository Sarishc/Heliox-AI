# Heliox OpenAPI Documentation

## Accessing the API Documentation

Heliox exposes OpenAPI 3.0 documentation at runtime:

| URL | Description |
|-----|-------------|
| `/docs` | Swagger UI (interactive) |
| `/redoc` | ReDoc (read-only) |
| `/openapi.json` | Raw OpenAPI JSON schema |

## Exporting OpenAPI Schema

To export the OpenAPI schema for offline use or client generation:

```bash
# Start the API
docker compose up -d api

# Export OpenAPI JSON
curl -s http://localhost:8000/openapi.json > openapi.json

# Or use Python
python -c "
from app.main import app
import json
with open('openapi.json', 'w') as f:
    json.dump(app.openapi(), f, indent=2)
"
```

## Client Generation

```bash
# Generate Python client (openapi-generator)
docker run --rm -v $(pwd):/local openapitools/openapi-generator-cli generate \
  -i /local/openapi.json -g python -o /local/clients/python

# Generate TypeScript client
npx @openapitools/openapi-generator-cli generate \
  -i openapi.json -g typescript-axios -o clients/ts
```

## Key API Groups

- **Auth** — Login, register, session
- **Teams** — Team management
- **Costs** — Cost snapshots, ingestion
- **Forecast** — Usage and spend forecasting
- **Optimize** — Recommendations
- **Integrations** — AWS, GCP connectors
- **Admin** — Team onboarding, API keys, demo seed
