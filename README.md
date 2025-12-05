# GPTKit

GPTKit is a unified backend designed to provide tools via HTTP Actions for Custom GPTs.

## Authentication

All endpoints require Bearer token authentication. The `GPTKIT_BEARER_TOKEN` environment variable **must** be set for the API to function (unless disabled in development mode).

### Usage

When calling the API, include the Bearer token in the `Authorization` header:

```bash
curl -H "Authorization: Bearer your-token-here" \
  "https://gptkit.guillaumeduveau.com/domain/whois?domain=example.com"
```

### Configuration

#### Production (Docker)

Use a `.env` file with Docker Compose (see [Deployment](#deployment) section):

```bash
# .env
GPTKIT_BEARER_TOKEN=your-secret-token-here
```

#### Local Development

For local development, you can disable authentication:

```bash
export GPTKIT_DISABLE_AUTH=1
uvicorn app.main:app --reload
```

Or set the token normally:

```bash
export GPTKIT_BEARER_TOKEN="your-secret-token-here"
uvicorn app.main:app --reload
```

## Tools

### WHOIS (`/domain/whois`)

Allows checking domain name availability and retrieving WHOIS information.

- **Endpoint**: `GET /domain/whois`
- **Parameters**:
  - `domain` (required): The domain name to check (e.g., `google.com`).
  - `refresh` (optional): `1` to force a fresh WHOIS lookup (ignores cache).
- **Features**:
  - Persistent cache (SQLite).
  - Rate limiting (global and per domain).
  - Automatic availability parsing for major TLDs.

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
    env_file:
      - .env
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

> **Security**: Never commit the `.env` file to version control. It's already in `.gitignore`. Copy `.env.example` to `.env` and set your values.

## Development

1. **Installation**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run**:
   ```bash
   uvicorn app.main:app --reload
   ```
3. **Tests**:

- Quick API smoke test (curl):
  ```bash
  # Without authentication (if GPTKIT_BEARER_TOKEN is not set)
  curl "http://localhost:8000/domain/whois?domain=example.com"
  
  # With authentication
  curl -H "Authorization: Bearer your-token-here" \
    "http://localhost:8000/domain/whois?domain=example.com"
  ```

- Run the unit test suite with pytest (from the project root):
  ```bash
  # activate your virtualenv if you have one, e.g.:
  source venv/bin/activate

  # install test/dev dependencies if needed
  pip install -r requirements.txt

  # run all tests
  pytest -q

  # run a single test file
  pytest tests/test_whois_parsing.py -q
  ```
