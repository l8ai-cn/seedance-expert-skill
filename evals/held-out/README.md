# Held-out suite boundary

No held-out prompt, assertion, case ID, fixture, asset, or author note belongs in this repository.

A held-out v2 manifest and its case pack must live together outside the candidate checkout. The manifest uses the portable schema URI and the same fields as `evals/suites/development.json`, sets `kind` to `held_out`, declares the future intent `release_eligible: true`, and names a case file contained in that external directory. Offline contract tests can parse such a pack, but the shipped V7-03 CLI refuses to execute any external suite and hard-locks the effective release gate off.

Release evaluation requires trusted harness code from the protected integration/default branch, an approved suite digest, and a boundary that never exposes the private corpus or provider credential to candidate-controlled code. Never use `pull_request_target` to execute candidate code, and publish only a redacted aggregate. Until that separate runner exists, no held-out execution or release gate is operational.
