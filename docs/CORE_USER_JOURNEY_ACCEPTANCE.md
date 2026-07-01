# Core SaaS User Journey Acceptance Checklist

Use this checklist for a real staging operator. Do not mark an item `PASS`
unless the action was performed against the intended staging environment and
the evidence path is recorded.

## Test Session

- Release candidate:
- Commit hash:
- Environment URL:
- Operator:
- Date:
- Evidence folder:
- Browser and device:

## Preconditions

- [ ] Staging compose or deployed staging environment is running.
- [ ] `/health/live` returns healthy.
- [ ] `/health/ready` returns healthy.
- [ ] Worker is running or the operator has recorded why worker checks are blocked.
- [ ] SMTP settings are configured, or fake/stub SMTP use is explicitly recorded for staging.
- [ ] The release evidence file is open and still uses `NOT_RUN` for unverified checks.

## Core Journey

- [ ] Register with a real test email address.
- [ ] Receive the verification email.
- [ ] Open the verification link and confirm it returns to login.
- [ ] Login with the verified account.
- [ ] Complete onboarding or confirm the existing onboarding state.
- [ ] Configure SMTP or confirm staging SMTP settings in the operator notes.
- [ ] Create or import a simple lead with email, name, title, and website.
- [ ] Review the lead list and confirm the lead appears.
- [ ] Open the lead detail or drawer and confirm contact information is readable.
- [ ] Change the CRM stage.
- [ ] Add a note or activity if the existing UI supports it.
- [ ] Prepare or send a test outreach message if staging SMTP is available.
- [ ] Confirm outreach status or feedback is visible without exposing sensitive errors.
- [ ] Confirm `/health/live`, `/health/ready`, and worker status after the journey.
- [ ] Record evidence location.

## Result

- PASS/FAIL:
- Known issues:
- Follow-up owner:
- Go/No-Go impact:
