# Optional Jev shadow triage

Status: local implementation, disabled by default. No live API call or quality
benchmark has been performed. This is advisory triage, never permission to apply.

## Contract and limits

The adapter uses the primary [TypeSafe OpenAPI 0.2.0 contract](https://api.typesafe.ai/openapi.json),
checked on 2026-10-01: POST /v1/systemone, named choice
questions, answers with confidence/probabilities, resolved model and token usage.
Choose a model available in your account; pin a version for the evaluation.
A valid schema does not imply a correct answer. The provisional 0.9 threshold
must be met by both confidence and the selected choice's probability; it is not
a calibrated accuracy claim.

The deterministic remote_gate verdict is preserved. FAIL skips the API; FLAG
always requires clarification. Missing salary, Brazil eligibility, contract or
hours must not be invented by a model. Jev's low_priority is advisory and never
removes a job. Provider errors, malformed replies and uncertain answers leave a
review item. The adapter does not change seen_jobs.json or the application CSV.

## Input and privacy

Prepare a private JSON outside Git containing ONLY posting_text (the public
posting) and candidate_summary (a minimal professional skills summary reviewed
by the user). Do not include contact details, raw CV, bank data, identity numbers,
mailbox contents, tokens or passwords. Free-text fields are not automatically
redacted; approval and input review are required before any live transmission.
Compute the reviewed factual gate with tools/remote_gate.py first and retain its
output locally. Never promote model guesses into reviewed gate evidence.

## Offline smoke test

Run `python -m unittest tests.test_jev_triage -v`.
The tests use synthetic inputs and mock responses; they make no network calls.
Run the CLI with --response-fixture for a local fixture evaluation, or omit both
--live and --response-fixture for a disabled result. A --model value is required.
Local JSON input, gate and fixture files accept UTF-8 with or without a BOM.

## Live activation (not performed)

Live mode needs BOTH --live and JEV_ENABLE_LIVE=1, plus TYPESAFE_API_KEY in the
runtime environment, entered by the user through a secure local setup. Do not
put credentials in command arguments, chat, Git or logs. The account, provider,
minimal profile disclosure and spending limit must be approved first.

One CLI invocation sends at most one request, capped to 24,000 bytes of serialized
UTF-8 input; the same serialization is used for validation, hashing and transport.
Timeout is 20 seconds and responses are capped at 65,536 bytes. Redirects and
automatic retries are disabled. A timeout may still be billable. Request size and
call count are NOT a guaranteed dollar cap. Until current billing and a spend
control are verified, do not run unattended batches. Provider output and errors
are not logged verbatim; results contain the verdict, probabilities, model, token usage
and an input hash. Store results outside Git.

## Workflow seam

At /rank Step 2, evaluate a reviewed candidate alongside the existing scoring
process. Treat this as a shadow comparison, not a replacement. Keep the original
scoring framework and rank_state writeback authoritative. Candidate/profile
changes require a fresh comparison; input_hash includes model and content.
Caching, batch scheduling and automatic promotion are intentionally not enabled
in this initial version.

## Evaluation before adoption

1. Label 100–200 representative public vacancies, including Brazil exclusion,
   ambiguous location, undisclosed/hourly salary, currency ambiguity, duplicate
   adverts, expired posts, prompt-injection text and adjacent skill matches.
2. Split by employer/role family; reserve a holdout before tuning the threshold.
3. Compare current triage, Jev and rules-only. Inspect disagreements manually.
4. Measure eligible-job recall (missed opportunities), top-k precision, review
   rate, per-field errors, confidence calibration, latency and actual token cost.
5. Predefine acceptance criteria after establishing the baseline. A small sample
   cannot prove safety; report uncertainty, all failures and holdout performance.
6. Enable an advisory queue only after user review; preserve the existing
   application confirmation flow, deterministic restrictions and rollback path.

## Rollout

Publishing or reviewing the code does not activate live mode. Keep it disabled
until the account, data scope and budget approval above are complete. Installation
in a private workspace and offline validation do not establish production quality
or authorize unattended operation.
