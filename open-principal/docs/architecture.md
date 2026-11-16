# Execution contracts, authority, evaluation

## Ownership and authority

**Human/org owner:** legal and operational principal, owns data and policy. **Participant:** holds one-time capability token; only this token can approve or decline a proposal, report an outcome, block a person, or withdraw. **Matcher:** may suggest or refuse a pair based on evidence, but cannot authorize contact release. **Operator:** may register users after obtaining their real opt-in, change the disclosed matching policy, and propose matches. The operator REST token cannot act as a participant token. The demonstration does not independently verify the registration assertion or a participant's claimed identity.

## End-to-end state machine

`enrolled -> proposal.refused | pending`. `pending -> accepted-by-one (still pending) -> introduced (both consent)`; `pending -> declined | expired | revoked | superseded`. `introduced -> outcome.recorded`. State changes are SQLite transactions and accompanied by a hash-chained event. There is no direct route from a recommendation to disclosed contact data. Blocking or revoking makes already-completed contact fields inaccessible through this application; it cannot undo the information a recipient previously learned.

## Matching algorithm (the full, deliberately simple baseline)

Tokenize the explicitly supplied `seeks` and `offers` strings into alphanumeric 3+-character tokens. Compute `A_seeks_B_offers = |A.seeks ∩ B.offers| / |A.seeks|`; similarly for B seeking A's offers. Accept a *candidate proposal*, not the actual introduction, iff both directional scores exceed `min_each_direction` and their sum exceeds `min_total_score` (default 0.10 and 0.20). Explain with the shared words; refuse pairs without evidence. Deny blocked pairs, duplicate pending offers, recent introductions inside the cooldown window, and participants at open-proposal capacity. All thresholds are versioned. This baseline is intentionally legible; it does not solve multilingual semantics, social risk, cold start, strategic self-promotion, or relational quality. A model can propose candidates, but the transactional boundary still enforces the published rules.

## Change transparency

A policy revision records its **content SHA-256**, increments version, and supersedes pending proposals. Each new candidate is stamped with the applicable policy version. Changes are inspectable, not unconditionally safe; the database operator can still rewrite history unless the previous chain head was independently witnessed. Publishing daily signed audit roots into a third-party archive would strengthen this property; cryptographic identity and signatures are outside this reference.

## Model independence

The deterministic matching and consent state machine do not call any model. A production semantic matcher may be swapped in to recommend candidates; it must receive only data it is authorized to access, cannot produce approval decisions, cannot write credentials, and cannot execute network messaging without explicit consent. All suggestions require provenance and reason codes; all actions require an authorization decision outside the model.

## Metrics that actually matter

Collect: valid mutual opt-in rate, contact disclosure violations (target zero), proposal-to-double-opt-in conversion, delayed consent, blocked and declined proposals, matches followed by positive/negative bilateral outcomes, complaints, policy-change invalidation, and observed downstream outcomes. Report denominator and confidence intervals. Account for selection bias and self-report. A claimed number of introductions or total connected people alone does not establish trust or economic value.

## Acceptance conditions

1. No participant credentials, no approval; a valid operator token alone cannot approve.
2. One approval does not disclose either address.
3. A refusal or block is final for that proposal, with a recorded reason/event.
4. A policy revision never upgrades old pending consent into a new authorization.
5. A revoked or erased participant's stored contact becomes inaccessible.
6. Event tampering is detectable, provided the original chain head has been externally anchored.
7. The service stays loopback-only unless a production gateway adds verified transport and authentication.

## Threats / explicit limits

| Threat | Current control | Not yet solved |
| --- | --- | --- |
| Unauthorized introduction | Separate participant tokens + transactional double opt-in | Participant identity proof, token theft, verified contact delivery |
| Silent model-policy change | Versioned hash + supersede outstanding proposals | Externally trusted notice delivery, cryptographic policy signing |
| Forged achievements and scraped profiles | Explicit registration + finite semantics | Identity verification, truth of claims, bot/fraud defense |
| Ledger rewriting | Canonical hash-chain audit | External anchoring, independent witnesses, trusted timestamping |
| Personal information spill | Contact withholding, local-only API, pseudonymous receipts | Encryption, compliance, access auditing, backup management |
| Inflated introductions | Two-sided outcomes and published failure denominator | Controlled evaluation, counterfactual quality, measured ROI |
| Unrestricted agent discretion | Deterministic authorized action boundary | Formal policy assurance and safe orchestration of external tools |
| Hidden legal responsibility | Explicit operator remains responsible | Jurisdiction-specific accountability, insurance and contracts |

## Why this isn't a literal autonomous principal

Neither the legal fiction of AI personhood nor personal pronouns create responsibility. This project treats the deploying organization as the liable principal and the software as a bounded decision-support agent. A persistent persona and reputation ledger are useful **without** inventing independent legal or moral status. Nothing here makes anthropomorphic representations or trust scores legally determinative.
