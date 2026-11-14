# REVIEW NEEDED — partners namespace (Urdu)

Strings I translated but am **not fully confident** about. Ordered by screen.
Nothing here is a machine translation; each item is a judgement call I want a
Lahore lab reviewer to confirm or replace.

## Cross-screen

| English source                                      | Urdu used                            | Why unsure                                                                                                                                                             |
| --------------------------------------------------- | ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Active for new accessions & referrals               | نئے accession اور ریفرلز کے لیے فعال | Glossary says `accession` stays English, but the mixed sentence ("نئے accession") reads awkwardly. A reviewer may prefer "نئے اندراجات" if the lab actually says that. |
| Specificity (column header)                         | خصوصیت                               | خصوصیت can be read as "specialness". No attested Urdu term for "specificity" exists in this repo.                                                                      |
| Deterministic Specificity Cascade                   | خصوصیت کے مطابق قطعی ترتیب           | Deliberately paraphrased. The "cascade" metaphor is lost; I used "order" (ترتیب) instead of inventing a word for cascade.                                              |
| Cascade evaluation hierarchy:                       | قواعد لاگو کرنے کی ترتیب:            | Simplified to "the order in which rules are applied". Literal "جھرنے دار درجہ بندی" would be dictionary Urdu nobody uses.                                              |
| Evaluation: (partner context strip)                 | جانچ:                                | I avoided تشخیص on purpose — in a lab, تشخیص reads as _diagnosis_, not "evaluation".                                                                                   |
| Partner-wide (specificity badge/heading)            | پارٹنر لیول                          | "لیول" (level) is used in Pakistani business Urdu, but it is a borrowing; the literal "پورے پارٹنر کے لیے" was too long for a badge.                                   |
| Unsettled                                           | غیر تصفیہ شدہ                        | Standard finance Urdu, but the shorter "باقی" is what some lab offices say.                                                                                            |
| Basis Amount (ledger column)                        | بنیادی رقم                           | Could be misread as "principal amount". "جس رقم پر حصہ ہے" is clearer but too long for a column.                                                                       |
| Indefinite (effective_to empty)                     | غیر معینہ                            | Correct but formal; "کوئی آخری تاریخ نہیں" is the spoken form.                                                                                                         |
| fallback (tenant fallback percentage, group 4 note) | fallback (Latin)                     | Kept English per rule 3; "فال بیک" in Urdu script was possible but no repo precedent.                                                                                  |

## Screen 36 — Referral Partners list

| English source               | Urdu used            | Why unsure                                                                                                                                                                                                                                          |
| ---------------------------- | -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| All statuses (filter option) | تمام حیثیتیں         | Grammatically correct plural of حیثیت but unusual in UI; many Pakistani products write "تمام اسٹیٹس".                                                                                                                                               |
| Financial Integrity Blocker  | مالی سالمیت کی رکاوٹ | "blocker" rendered as رکاوٹ (obstacle). A reviewer may prefer "مالی سالمیت کی روک".                                                                                                                                                                 |
| Retry (error banner)         | دوبارہ کوشش کریں     | I did **not** reuse `common:actions.retry` ("Try again") because the original English button says "Retry" — rule 1 requires byte-identical English. Flagging the inconsistency: en now has two near-duplicate retry labels in different namespaces. |

## Screen 37 — Partner detail

| English source                                                                  | Urdu used                                                       | Why unsure                                                                                              |
| ------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Independent Referral (no organisation)                                          | آزاد ریفرل                                                      | Awkward as a value. "خود مختار ریفرل" or keeping "Independent Referral" English are both plausible.     |
| Real-time commission accruals and settlement history derived from tenant ledger | ٹیننٹ لیجر سے حاصل کردہ ریئل ٹائم کمیشن جمع اور تصفیوں کی تاریخ | "ریئل ٹائم" is a borrowing, not pure Urdu, but it is what lab staff actually say; "وقتی" was ambiguous. |
| Fully paid and disbursed to partner                                             | پارٹنر کو مکمل ادا اور تقسیم شدہ                                | Grammatically tight but terse; no verb agreement to check against.                                      |
| Awaiting upcoming settlement cycle                                              | آنے والے تصفیہ سائیکل کا انتظار                                 | "سائیکل" borrowed; "آنے والے تصفیے کا انتظار" loses the cycle meaning.                                  |
| Stakeholder wording in rules-editor note                                        | … اسکرین 38 (Rules Editor) میں سنبھالی جاتی ہے۔                 | "Rules Editor" kept English inside the Urdu sentence (product surface name).                            |

## Screen 38 — Rules

| English source                                                      | Urdu used                                                | Why unsure                                                                                                                   |
| ------------------------------------------------------------------- | -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| retire this rule (confirm dialog)                                   | بند کرنا                                                 | Source says "retire", Urdu says "close" (بند). "ریٹائر کرنا" sounded wrong in Urdu; chose consistency with the Close action. |
| Strict resolution order                                             | قطعی ترتیب                                               | Drops "resolution"; could read as just "definite order".                                                                     |
| Priority 1 · Matches both branch facility and clinical test section | (ترجیح 1 · برانچ اور کلینیکل ٹیسٹ سیکشن دونوں سے مطابقت) | "clinical test section" rendered as "کلینیکل ٹیسٹ سیکشن" (borrowed); "شعبہ" would be more Urdu but less precise here.        |
| Catch-all default (group 4 note)                                    | عمومی ڈیفالٹ                                             | "ڈیفالٹ" borrowed; "طے شدہ" loses the "default" meaning.                                                                     |
| Validity Period                                                     | لاگو مدت                                                 | "validity" as لاگو (applicable) — chosen over "اعتبار" which is rarer in ops UIs.                                            |
| Immutable History:                                                  | ناقابلِ تبدیل تاریخ:                                     | تاریخ here means "history", not "date" — could be misread as a date label.                                                   |

## Screen 39 — Share ledger

| English source                                     | Urdu used                                                    | Why unsure                                                              |
| -------------------------------------------------- | ------------------------------------------------------------ | ----------------------------------------------------------------------- |
| Append-only — entries cannot be edited or deleted. | صرف اضافے کی اجازت — اندراجات میں ترمیم یا حذف نہیں ہو سکتا۔ | "Append-only" is a technical phrase with no short Urdu equivalent.      |
| Recorded Shares                                    | درج شدہ حصے                                                  | Plural "حصے" may read as "portions"; context makes it revenue shares.   |
| Filtered Period                                    | فلٹر شدہ مدت                                                 | "مدت" (duration) for a billing _period_ (YYYY-MM); "دورانیہ" was worse. |
| All periods                                        | تمام ادوار                                                   | ادوار is the correct plural of دور but sounds literary.                 |
| Audit Lock: Active                                 | آڈٹ لاک: فعال                                                | "Lock" kept as borrowing; "آڈٹ مقفل" was an alternative.                |
| Payment Ref                                        | ادائیگی ریفرنس                                               | "Ref" expanded to ریفرنس; column width may need checking.               |

## Screen 40 — Partner dashboard

| English source                     | Urdu used                                 | Why unsure                                                                                                         |
| ---------------------------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| YTD Earned / YTD Settled           | YTD حاصل شدہ / YTD تصفیہ شدہ              | `YTD` kept as an abbreviation (no Urdu equivalent in use). "حاصل شدہ" for "earned" may read as "obtained".         |
| Accrued revenue share year to date | سال کے آغاز سے اب تک جمع شدہ آمدنی کا حصہ | Long; "سال بہ سال" would be wrong (that means year-on-year).                                                       |
| Post-cutoff prior period entries   | کٹ آف کے بعد پچھلی مدت کے اندراجات        | "cutoff" as کٹ آف (borrowed).                                                                                      |
| Late Entries                       | دیر سے آنے والے اندراجات                  | Source means entries that arrived after the settlement cutoff, not "late" in a general sense; the Urdu is literal. |

## Deliberately left in English (not translated)

1. **CSV export headers** in `LedgerScreen.tsx` (`ID`, `Created At`,
   `Payment ID`, `Partner Name`, `Basis Amount (PKR)`, `Percent Applied`,
   `Commission (PKR)`, `Period`, `Settlement Status`, `Settlement Period`) and
   the `UNSETTLED` cell fallback. Reason: this is a finance file opened in
   Excel, not screen copy, and the download uses a `data:text/csv` URI with no
   UTF-8 BOM — Urdu headers would render as mojibake on Windows Excel. If a
   reviewer wants them localised, the export needs a BOM first.
2. **Data**: partner/lab/branch names, ids, phones, emails, money amounts,
   percentages, dates, `PAID`/`APPROVED`/`DRAFT`/`UNSETTLED` status tokens, test
   category names (`Haematology`, `Biochemistry`, `Molecular`), `PKR`, `PDF`,
   `WhatsApp`, `RR-3`, `422 rule_overlap`, `effective_from`/`effective_to`,
   `YTD`, `ID`, `CSV`, `IS`-style identifiers — all treated as data or
   technical tokens per rules 3 and 4.
3. **`Registered on`** still uses `new Date(...).toLocaleDateString()` and the
   ledger date cell still uses the inline `en-GB` `toLocaleString` (comma
   stripped). `formatDate`/`formatDateTime` produce a different shape
   (`12 Jan 2026` / `19 Oct 2026, 17:15`), so switching would change the
   displayed format. Flagged instead of changed (rule 9).
4. **`Failed to close rule`** previously appended the raw server `message`;
   it now shows a fixed translated sentence, per rule 10 (never render server
   `detail` verbatim). Same for the rule-overlap / retroactive-date branches,
   which keep their English-identical wording plus translated Urdu.
