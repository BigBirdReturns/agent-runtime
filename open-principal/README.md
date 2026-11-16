# Open Principal Stack

**An entire reference implementation of a consent-bound AI-introduction service, released free under MIT.** No proprietary code or private relationship data from Boardy or any other vendor. The term *principal* here is an architectural discussion, **not a claim of AI personhood, legal capacity, independent moral agency, or actual human trust**. Responsibility remains with the deploying organization.

A response to Andrew D'Souza's *Principals* and Boardy's *Am I the world's first AI principal?* (both November 2026). Their strongest technical insight is that hidden changes to an agent's decision rules undermine the relationships it appears to maintain. This project makes those changes observable and gives participants enforceable, consent-specific authority to say no.

## Quick start: offline, no account, no API key, no dependencies

```bash
python3 principal.py demo
python3 -m unittest discover -s tests -v
```

The demo creates two opted-in fictional participants, proposes a mutually relevant introduction, proves that neither address is released after the first approval, releases both only after the second, records an outcome, and verifies the event log.

## What's included

- **Stable identity**: persistent SQLite participant identifiers, one-time participant capability tokens (stored as hashes), and retained history across restarts.
- **Open matching logic**: transparent bidirectional token-overlap relevance, explanations listing matching terms, policy thresholds, and a refusal outcome when evidence is inadequate. No mystery ranker. Substitute a semantic ranker as a **proposal signal**, never as authorization.
- **Mutual consent**: distinct participant tokens, independent accept/decline, seven-day expiration, no contact disclosure before both approvals. A person can block another or revoke enrollment.
- **Actual policy governance**: numbered, hashed policies; every change produces a ledger event and automatically supersedes pending proposals so old consent cannot silently authorize new criteria.
- **Counterparty outcomes**: {-1,0,+1} ratings and free-text notes; notes are excluded from public receipts; reputation estimates are withheld until at least five counterpart reports. Self-report is explicitly not treated as verified economic outcome.
- **Auditable refusals**: a failed match has a reason and an event, as do consent declines, expiry, policy changes, revocations, and introductions.
- **Receipt chain**: SHA-256 canonical event chaining, full public pseudonymous receipt export, and standalone independent verification script. Publish the chain head to an independently controlled system to make subsequent database rewriting observable. **A hash chain without independent anchoring is not tamperproof.**
- **Authenticated loopback API**: stdlib HTTP server, admin bearer token for operator actions, participant tokens for decisions, no permissive CORS, no public network bind, no silent participant impersonation by the operator HTTP route.
- **Tests**: exercise refusal, bilateral consent, policy changes, blocks, erasure, tampering, expiration, authenticated API behavior and persistence.

## Command-line examples

```bash
# In a new folder, initialize automatically with the first command.
python3 principal.py --db demo.db policy

# Only register someone who has opted in to being matched; each returns a
# one-time token that must be delivered privately to the person.
python3 principal.py --db demo.db register --name Alice --seeks 'thermal engineering' --offers 'optics imaging' --contact 'alice@example.org' --opt-in
python3 principal.py --db demo.db register --name Bob --seeks 'optics imaging' --offers 'thermal engineering' --contact 'bob@example.org' --opt-in

python3 principal.py --db demo.db propose ALICE_ID BOB_ID
# Participants provide their own secret tokens through an environment variable.
PRINCIPAL_TOKEN='ALICE_TOKEN' python3 principal.py --db demo.db decide PROPOSAL_ID --accept
PRINCIPAL_TOKEN='BOB_TOKEN' python3 principal.py --db demo.db decide PROPOSAL_ID --accept
PRINCIPAL_TOKEN='ALICE_TOKEN' python3 principal.py --db demo.db show PROPOSAL_ID
python3 principal.py --db demo.db audit
python3 principal.py --db demo.db export-receipts --output audit-public.json
python3 verify_receipts.py audit-public.json --expected-head HEAD_FROM_INDEPENDENT_ARCHIVE
python3 principal.py --db demo.db set-policy --json '{"min_total_score":0.5}'
```

The `--token` CLI option exists for convenience but may expose secrets in process listings and shell history; `PRINCIPAL_TOKEN` is preferable. Do not commit database files or participant tokens to git. Demo emails use `*.invalid` and never send mail.

## Local JSON API

```bash
export PRINCIPAL_OPERATOR_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
python3 server.py --db principal.db --port 8765
curl -s http://127.0.0.1:8765/policy -H "Authorization: Bearer $PRINCIPAL_OPERATOR_TOKEN"
```

Operator-only routes: `POST /register`, `POST /propose`, `POST /policy`, `GET /policy`, `GET /audit`, `GET /receipts`, `GET /metrics`, `GET /reputation/{id}`, `GET /health`. Participant-only routes: `GET /proposal/{id}`, `POST /decide`, `POST /feedback`, `POST /block`, `POST /revoke`, `POST /erase`. Operator has no HTTP override for participant decisions. See `docs/architecture.md` for state transitions and authorization.

The server binds loopback only. It is an inspectable **reference**, not a production service. Before handling real people, add verified identities and enrollment, transport security, encrypted storage, fine-grained operator roles, rate limiting, explicit consent UX, notification delivery, independent audit anchoring, abuse reporting, request provenance, backups and backup erasure, retention rules, compliance review, and monitoring. The demo does **not** implement connectors to proprietary networks, voice, messaging, calendar, or large-model inference.

## What the original essays left unresolved

D'Souza's four tests are social and economic claims. Boardy's own article identifies a stronger technical failure: an operator can silently reprogram the apparent friend. We implement the necessary foundation: a policy hash, policy-update receipt, invalidation of pending approvals, and an authority boundary the LLM cannot bypass. This is not sufficient for trust. Verified identity, reliable delivery, judicial recourse, external auditing, and observed bilateral outcomes are separate requirements.

Their company describes an accumulated network as an advantage. **The private network, not the matching algorithm, is the non-copyable asset.** This repository gives away the matching, consent, governance, refusal, audit, data-model, API, and test code; it does not expose other people's information or claim to reproduce Boardy's proprietary implementation.

## Sources and provenance

- Andrew D'Souza, [*Principals*](https://www.boardy.ai/principals), November 13, 2026.
- Boardy, [*Am I the world's first AI principal?*](https://x.com/boardyai/article/2122395956738232683), November 16, 2026.
- [Boardy terms](https://www.boardy.ai/terms-and-conditions) (published double opt-in and operator responsibility are compared as external facts, not copied source code).

Independent clean-room reference written from public conceptual descriptions; no access to or representation of Boardy's proprietary code. No affiliation or endorsement.

## License

MIT: copy, run, modify and redistribute free, including commercial use. See [LICENSE](LICENSE).