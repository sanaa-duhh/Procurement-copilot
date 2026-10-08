# Submission checklist

## Verified locally

- [x] Both architectures run through the starter-compatible adapter.
- [x] UI includes request details, verified evidence, recommendation and human action.
- [x] Saved architecture comparison is browsable in the app without paid calls.
- [x] Input changes clear stale results; review saves and downloads do not rerun analysis.
- [x] Seven deterministic tools have locally validated input schemas.
- [x] Policy checks enforce thresholds, budget, vendor dates/conflicts and required reviews.
- [x] Structured model outputs are locally validated; tool loops are bounded.
- [x] Missing information, injected instructions and unavailable evidence are exercised in tests.
- [x] Human decisions reference the exact request and analysis run.
- [x] Tests and scripted comparison run without model credentials or a listening API.
- [x] One-command demo, locked dependencies, CI and .env.example are provided.
- [x] Architecture diagrams, assumptions, limitations and reviewer walkthrough are documented.

## Required before submitting the URL

- [x] Verify OpenAI model access using the existing shell credential.
- [x] Run both architectures on the same cases; retain complete results and failures.
- [x] Inspect raw drafts, grounding, latency/calls/tokens and architecture disagreements.
- [x] Replace the provisional memo with a results-backed ship decision (≤500 words).
- [x] Fill the README comparison from the real artifacts and remove pending notices.
- [ ] Owner: create/push the public GitHub repository and check the URL while signed out.
- [x] Confirm no credentials or private runtime review logs are tracked.
- [ ] Submit the public repository URL through the [assignment form](https://forms.gle/ab9DrohuNQWukXCD9) before 8 October, 11:59 PM.
