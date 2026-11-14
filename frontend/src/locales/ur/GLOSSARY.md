# Urdu glossary — LabFlow staff UI

One Urdu word per English term, used in all ten namespaces. This file is the
authority for reviewers: if a screen disagrees with this table, the screen is
wrong.

Only repo-attested Urdu is treated as known-good today: رپورٹ, آپ کی رپورٹ تیار
ہے, سوالات کے لیے رابطہ کریں, لیب فلو, لیب فلو میں خوش آمدید, آپ کی لیب رپورٹ
تیار ہے. Everything else below is a reviewed choice, not a machine translation.

## Clinical and operational terms

| English                    | Urdu (use everywhere)      | Notes                                                    |
| -------------------------- | -------------------------- | -------------------------------------------------------- |
| lab                        | لیب                        | لیب فلو for the product name                             |
| patient                    | مریض                       | never پیشنٹ                                              |
| report                     | رپورٹ                      | attested                                                 |
| result                     | نتیجہ                      | plural نتائج                                             |
| sample                     | نمونہ                      | plural نمونے                                             |
| test                       | ٹیسٹ                       | test names themselves are clinical data and stay English |
| test panel                 | ٹیسٹ پینل                  | panel names stay English                                 |
| accession / accession ID   | accession                  | keep the English word, Latin script; never invent        |
| MRN                        | MRN                        | keep the English abbreviation                            |
| reference range / interval | حوالہ رینج                 | the values stay exactly as returned                      |
| flag H / L / Critical      | H / L / Critical           | flag letters are clinical data, never translated         |
| amended report             | ترمیم شدہ رپورٹ            |                                                          |
| pathologist approval       | پیتھالوجسٹ کی منظوری       |                                                          |
| branch                     | برانچ                      | plural برانچیں                                           |
| referral partner           | ریفرل پارٹنر               |                                                          |
| revenue share              | آمدنی کا حصہ               |                                                          |
| ledger                     | لیجر                       |                                                          |
| settlement                 | تصفیہ                      | plural تصفیے                                             |
| invoice                    | بل                         | receipt = رسید                                           |
| refund                     | رقم واپسی                  |                                                          |
| discount                   | رعایت                      |                                                          |
| overdue                    | مدت گزری                   |                                                          |
| TOTP / authenticator       | authenticator / TOTP       | keep English                                             |
| worklist                   | ورک لسٹ                    |                                                          |
| collection / collected     | نمونہ لینا / نمونہ لیا گیا |                                                          |
| received                   | موصول                      |                                                          |
| in process                 | زیر عمل                    |                                                          |
| ready                      | تیار                       |                                                          |
| rejected                   | مسترد                      |                                                          |
| cancelled                  | منسوخ                      |                                                          |
| awaiting collection        | نمونے کے منتظر             |                                                          |
| critical value             | critical value             | keep English in a clinical sentence                      |
| reference clinician        | ریفرنگ کلینشین             |                                                          |

## UI verbs and labels

| English       | Urdu         |
| ------------- | ------------ |
| Save          | محفوظ کریں   |
| Cancel        | منسوخ کریں   |
| Back          | واپس         |
| Next          | اگلا         |
| Submit        | جمع کریں     |
| Edit          | ترمیم        |
| Delete        | حذف کریں     |
| View          | دیکھیں       |
| Close         | بند کریں     |
| Search        | تلاش         |
| Filter        | فلٹر         |
| Reset         | ری سیٹ       |
| Print         | پرنٹ کریں    |
| Download      | ڈاؤن لوڈ     |
| Refresh       | تازہ کریں    |
| Confirm       | تصدیق کریں   |
| Settings      | ترتیبات      |
| Dashboard     | ڈیش بورڈ     |
| Sign in       | سائن ان      |
| Sign out      | سائن آؤٹ     |
| Password      | پاس ورڈ      |
| Email         | ای میل       |
| Language      | زبان         |
| Status        | حیثیت        |
| Actions       | کارروائیاں   |
| Amount        | رقم          |
| Total         | کل           |
| Date          | تاریخ        |
| Time          | وقت          |
| Age           | عمر          |
| Sex           | جنس          |
| Date of birth | تاریخ پیدائش |
| Not recorded  | درج نہیں     |

## Invariants

- Digits are Latin 0–9 everywhere. Never Eastern Arabic or Persian digits.
- Months stay English (`20 Oct 2026`) in both languages.
- Money is `PKR 1250.00` in English and `روپے 1250.00` in Urdu, verbatim amount.
- Patient names, lab names, branch names, partner names, clinician names,
  accession IDs, MRNs, phone numbers, emails, URLs, result values, units and
  dates are data: never translate them. Wrap Latin/digit runs in
  `<bdi dir="ltr">` (or `dir="ltr"`) inside Urdu sentences.
- Test names, panel names, reference intervals, flags and units are clinical
  data: never translate them, in UI or PDF.
- Nastaliq is display only (headings/titles, ≥18px). Tables, buttons, inputs,
  labels and toasts use Noto Sans Arabic.
- If there is no good Urdu word, keep the English word in Latin script. That is
  correct; an invented Urdu word is a defect.
