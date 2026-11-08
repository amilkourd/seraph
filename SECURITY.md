# Security

## Reporting a vulnerability

Report vulnerabilities privately through GitHub (**Security → Report a vulnerability** on this repository), not in
a public issue. Include the affected module, the steps to reproduce and the impact.

## How Seraph handles sensitive data

- **Secrets** come only from environment variables (`.env`, template in `.env.example`). `.env` is never committed
  and keys are never logged.
- **Phone numbers** are masked in logs and in what Gabriel sends to Seraph.
- **Occupant data** is used only for the incident in progress, and every read of the occupant list is logged.
- **Computer use** reads public sites read-only and writes only in systems it is authorised to operate. Rosetta
  never solves or bypasses a CAPTCHA.
- **Orders** to occupants, reroutes and the incident report require the commander's confirmation and expire after
  2 minutes ([docs/07-safety-rules.md](docs/07-safety-rules.md)).
