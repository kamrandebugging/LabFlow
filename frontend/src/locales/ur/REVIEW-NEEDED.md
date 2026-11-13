# REVIEW-NEEDED — Urdu strings the implementer is not fully confident about

Owner (native speaker) reviews this list before merge. Do not hide uncertainty.

Format: screen/file — English source — Urdu used — why unsure.

| Area     | File / screen        | English source                                     | Urdu used                                          | Why unsure                                                            |
| -------- | -------------------- | -------------------------------------------------- | -------------------------------------------------- | --------------------------------------------------------------------- |
| PDF      | report Urdu block    | "Your report is ready"                             | آپ کی رپورٹ تیار ہے                                | repo-attested, no review needed                                       |
| Common   | status.flag.critical | Critical                                           | Critical                                           | kept English to avoid a wrong clinical nuance; confirm lab convention |
| Common   | invoice              | Invoice                                            | بل                                                 | labs also say انوائس; confirm preferred term                          |
| Settings | language.help        | Saved on this device only…                         | صرف اسی ڈیوائس پر محفوظ ہوتی ہے…                   | natural but confirm register                                          |
| Auth     | TOTP guidance        | Enter the 6-digit code from your authenticator app | اپنی authenticator ایپ سے 6 ہندسوں کا کوڈ درج کریں | keeps authenticator in English by design; confirm readability         |

## Per-area lists (full detail)

Every area keeps its own honest uncertainty register next to the locale files:

- `REVIEW-NEEDED-auth.md` — auth, TOTP, enrolment, forced password change
- `REVIEW-NEEDED-patients.md`
- `REVIEW-NEEDED-billing.md`
- `REVIEW-NEEDED-samples.md`
- `REVIEW-NEEDED-results.md`
- `REVIEW-NEEDED-reports.md` — public report page, reports list/detail, exceptions
- `REVIEW-NEEDED-partners.md`
- `REVIEW-NEEDED-settlements.md`
- `REVIEW-NEEDED-settings.md` — tenant settings, branches, account, exports, staff, catalog
- `REVIEW-NEEDED-dashboards.md` — Owner, Manager, Receptionist, Technician, Pathologist

## Known limitations (not translation defects)

- **Public report page tenant default**: the public report-access endpoint returns
  only a 302 to the signed PDF; it exposes no `report_default_language`. The page
  therefore resolves explicit choice → browser language → English, and
  `resolvePublicLanguage(tenantDefault)` is ready for the tenant value as soon as
  a public metadata field exists. No fake value is invented.
- **Screenshots**: the gates in this run produced component tests, a real WeasyPrint
  PDF render (Urdu block + Nastaliq glyph/clipping proof), and targeted backend
  tests. Per-screen Urdu screenshots require a running seeded tenant and were not
  captured in this session; the demo tenant (`demo-lhr`) is seeded if the reviewer
  wants to repeat them.
- **CSV ledger export** stays English by design: the `data:text/csv` download has
  no UTF-8 BOM, so Urdu headers would be mojibake in Excel.

