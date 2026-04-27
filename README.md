# GPTKit

GPTKit is a unified backend designed to provide tools via HTTP Actions for Custom GPTs.

## Authentication

All endpoints require Bearer token authentication. The `GPTKIT_BEARER_TOKEN` environment variable **must** be set for the API to function (unless disabled in development mode).

### Usage

When calling the API, include the Bearer token in the `Authorization` header:

```bash
curl -H "Authorization: Bearer your-token-here" \
  "https://gptkit.guillaumeduveau.com/domain/availability?domain=example.com"
```

### Configuration

#### Production (Docker)

Use a `.env` file with Docker Compose (see [Deployment](#deployment) section):

```bash
# .env
GPTKIT_BEARER_TOKEN=your-secret-token-here
```

#### Local Development

GPTKit now targets Python 3.14+ and uses `uv` for all local commands.

For local development, you can disable authentication:

```bash
export GPTKIT_DISABLE_AUTH=1
uv run uvicorn app.main:app --reload
```

Or set the token normally:

```bash
export GPTKIT_BEARER_TOKEN="your-secret-token-here"
uv run uvicorn app.main:app --reload
```

## Tools

### Domain Availability (`/domain/availability`)

Checks whether a single domain is available, with a response shape optimized for Custom GPT Actions.

- **Endpoint**: `GET /domain/availability`
- **Parameters**:
  - `domain` (required): Full domain name including TLD, for example `example.com` or `monsite.fr`.
- **Features**:
  - Persistent cache (SQLite).
  - Rate limiting (global and per domain).
  - Internal WHOIS collection kept for caching, without exposing WHOIS details in the public response.
  - Stable single-domain response for GPT Actions.

Example response:

```json
{
  "domain": "example.com",
  "available": true,
  "status": "ok"
}
```

## Deployment

### Docker Compose

Here is an example `docker-compose.yml` configuration to deploy GPTKit.

> **Note**: The image is available on GHCR. Make sure to replace `your-username` with your GitHub username.

```yaml
services:
  gptkit:
    image: ghcr.io/your-username/gptkit:latest
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - GPTKIT_BEARER_TOKEN=${GPTKIT_BEARER_TOKEN}
    volumes:
      # Data persistence (WHOIS cache stored in /app/data/whois_cache.db)
      - gptkit_data:/app/data

volumes:
  gptkit_data:
```

Create a `.env` file in the same directory as `docker-compose.yml` (see `.env.example` for reference):

```bash
# .env (do not commit this file!)
GPTKIT_BEARER_TOKEN=your-secret-token-here
```

Docker Compose will automatically load variables from the `.env` file or from the host environment.

> **Security**: Never commit the `.env` file to version control. It's already in `.gitignore`. Copy `.env.example` to `.env` and set your values.

## Development

1. **Installation**:
   ```bash
   uv sync --dev
   ```

2. **Run**:
   ```bash
   uv run uvicorn app.main:app --reload
   ```
3. **Tests**:

- Quick API smoke test (curl):
  ```bash
  # Without authentication (if GPTKIT_BEARER_TOKEN is not set)
  curl "http://localhost:8000/domain/availability?domain=example.com"
  
  # With authentication
  curl -H "Authorization: Bearer your-token-here" \
    "http://localhost:8000/domain/availability?domain=example.fr"
  ```

- Run the unit test suite with pytest (from the project root):
  ```bash
  # sync the project environment
  uv sync --dev

  # run all tests
  uv run pytest -q

  # run a single test file
  uv run pytest tests/test_whois_parsing.py -q
  ```
