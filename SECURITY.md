# Security Policy

StockAI handles authentication credentials, API provider keys, and market data.
If you discover a security vulnerability:

1. **Do not** open a public issue with exploit details.
2. Contact the repository maintainers privately with:
   - affected component and version/commit
   - reproduction steps
   - impact assessment
3. Allow reasonable time for a fix before any disclosure.

## Scope notes

- Secrets (`SECRET_KEY`, provider API keys, database credentials) are
  environment-provided and never committed; see `.env.example`.
- Production deployments must set `BACKEND_CORS_ORIGINS` explicitly and run a
  single `api` replica unless Valkey-backed coordination is reviewed.
- There is no bug-bounty program.
- Predictive outputs are research estimates with documented modest evidence;
  they are not investment advice (see README disclaimer).
