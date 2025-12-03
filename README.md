# GPTKit

GPTKit is a unified backend designed to provide tools via HTTP Actions for Custom GPTs.

## Tools

### WHOIS (`/domain/whois`)

Allows checking domain name availability and retrieving WHOIS information.

- **Endpoint**: `GET /domain/whois`
- **Parameters**:
  - `domain` (required): The domain name to check (e.g., `google.com`).
  - `force` (optional): `1` to force a fresh WHOIS lookup (ignores cache).
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
    volumes:
      # Data persistence (WHOIS cache stored in /app/data/whois_cache.db)
      - gptkit_data:/app/data

volumes:
  gptkit_data:
```

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
  curl "http://localhost:8000/domain/whois?domain=example.com"
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
