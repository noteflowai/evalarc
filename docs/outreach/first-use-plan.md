# First-use validation plan · 2026-09-16

Focus on Agent developers reviewing a change before accepting it. The primary
example is the recorded score increase from 90% to 93.75% with a regressed
notes check. Keep the three-step path visible: inspect, review locally, try
one's own evidence.

## Ready for independent use

- English and Chinese first-review guides use the public 0.12.1 wheel and
  original release files. They do not require a source checkout or Docker.
- Maintainer verification in a fresh virtual environment outside the checkout
  reproduced the regression, suite decisions and trace imports. Restricting
  PATH to that environment left no Docker or Node available to those commands.
- The 30-second media uses actual UI screenshots with original evidence
  fingerprints. It does not depict a new agent run.
- The first-use issue form asks for the intended decision, first failure,
  environment and practical value, using a minimal redacted example.
- Current editorial drafts are tailored to their channels. HelloGitHub's
  description is 153 characters, within its current 32–256 requirement.

These are maintainer checks and prepared invitations, not independent adoption.
The scored AgentCore-shaped controls remain synthetic; live service collection
has not been validated.

## Next seven days

1. Keep the existing HF introduction and editorial submissions aligned with
   the deployed guide. Read edits back; pending submissions are not listings.
2. Seek three independent first-use attempts with a real review question.
   Record setup failures and unsupported formats alongside successful imports.
3. Prioritize fixes that unblock those attempts. Add adapters only for an
   actual export format, with a redacted fixture and explicit semantics.
4. Publish a reproducible finding when a user can share one; never relabel
   synthetic controls as customer evidence or manufacture usage reports.
5. Review at the end of the week: did anyone use a second record, change a
   decision, report a concrete blocker, or contribute an example?

Three participants is a validation target, not a promised growth outcome.
Maintenance checks, CI clones and release-download verification are logged
separately from independent use. Do not calculate conversion by mixing
GitHub's traffic window with cumulative Stars or attachment downloads.

Use aggregate channel analytics only where available. No trace upload or
client tracking was added in this update.
