# REVIEW NEEDED — samples namespace (Urdu)

Translator notes for `frontend/src/locales/ur/samples.json`.
Everything here is a reviewed choice, **not** machine translation, but these are
the strings a native Lahore reviewer should look at first. File paths are the
five screens translated: `SampleAccessioningListScreen`, `CollectSampleStep1Screen`,
`CollectSampleStep2Screen`, `SampleDetailScreen`, `SampleLabelScreen`.

Legend: **key** — where it appears; **English** — source that tests/users see in
`en`; **Urdu used**; **why unsure**.

## 1. Terminology choices that are not in GLOSSARY.md

| key                                 | English                                       | Urdu used                                | Why unsure                                                                                                                                                                               |
| ----------------------------------- | --------------------------------------------- | ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `breadcrumbs.aria`                  | Breadcrumb                                    | بریڈ کرمب                                | Transliteration, not a native Urdu term. Alternative: صفحے کا راستہ. Screen-reader users in Pakistan are used to بریڈ کرمب, but this is a judgement call.                                |
| `actions.lookup`                    | Lookup                                        | حاصل کریں                                | "Lookup" is a fetch, not a search. حاصل کریں is neutral; a Lahore receptionist might expect بل تلاش کریں (but that duplicates the search field) or بل کھولیں.                            |
| `list.all_statuses`                 | All statuses                                  | تمام حیثیتیں                             | Plural of حیثیت. Correct grammar, but many staff say تمام اسٹیٹس. Glossary fixes Status = حیثیت, so the plural was formed from it.                                                       |
| `verify.accessioning`               | Accessioning...                               | accession ہو رہا ہے...                   | "Accessioning" is a verb with no Urdu equivalent (glossary keeps _accession_ English). Mixed-script sentence is deliberate; check it reads naturally on the button.                      |
| `detail.back_to_accessioning`       | Back to Accessioning                          | accessioning پر واپس جائیں               | Same reason as above — the screen name itself is "accessioning".                                                                                                                         |
| `collect.collected_by_hint`         | Authenticated intake operator                 | تصدیق شدہ انٹیک آپریٹر                   | "intake operator" transliterated. Alternative: تصدیق شدہ اندراج آپریٹر, which sounds clerical rather than clinical.                                                                      |
| `collect.collected_at_hint`         | Current phlebotomy timestamp                  | فلیبوٹومی کا موجودہ وقت                  | phlebotomy is transliterated (فلیبوٹومی); "timestamp" simplified to وقت instead of ٹائم اسٹیمپ because the label above already says وقت.                                                 |
| `detail.phlebotomy_station_default` | Phlebotomy Station #01                        | Phlebotomy Station #01                   | Left English on purpose: it is a station identifier (like a branch name) shown when `collected_by` is empty.                                                                             |
| `verify.station_name`               | Phlebotomy Counter 02                         | Phlebotomy Counter 02                    | Left English on purpose: physical counter name, same class of data as a branch or bench name.                                                                                            |
| `verify.specimen_whole_blood`       | Whole Blood                                   | Whole Blood                              | Specimen types also arrive from the API as clinical data (`specimen_type` on the detail screen) and stay English there; translating only this badge would make the two screens disagree. |
| `verify.specimen_plasma_blood`      | Plasma / Blood                                | Plasma / Blood                           | Same reason as Whole Blood.                                                                                                                                                              |
| `detail.current_custody`            | Current Physical Custody                      | موجودہ جسمانی تحویل                      | "Physical custody" is legal-logistics language; جسمانی تحویل is the literal-but-used rendering.                                                                                          |
| `detail.custody_fallback`           | {{branch}} — Specimen Bench A                 | {{branch}} — نمونہ بینچ A                | Bench name invented in the original code; kept the letter "A". The physical bench sign in the lab says "Specimen Bench A", so a reviewer may prefer to leave the whole caption English.  |
| `detail.rack_slot_fallback`         | Rack 04 / Slot 12                             | ریک 04 / سلاٹ 12                         | Storage location placeholder. سلاٹ is understood in Pakistani labs; alternative: خانہ.                                                                                                   |
| `detail.transfer_branch_label`      | Destination Branch / Lab *                    | منتقلی کی منزل: برانچ / لیب *            | Urdu needed a colon + "منتقلی کی منزل" (destination of the transfer) to read naturally; the English has no colon. Check the modal still looks right.                                     |
| `detail.main_lab`                   | Main Lab                                      | مرکزی لیب                                | This is a _fallback branch name_; branch names are data elsewhere. If reviewers prefer, it should stay "Main Lab".                                                                       |
| `verify.labels_queued`              | Primary Barcode Labels Queued                 | پرائمری بارکوڈ لیبل قطار میں             | "Queued" — قطار میں is the everyday word; باری پر or قطار میں منتظر also possible.                                                                                                       |
| `verify.printer_ready`              | Zebra ZD410 Thermal Printer · Ready on Tray 1 | Zebra ZD410 تھرمل پرنٹر · Tray 1 پر تیار | Device model kept Latin; "Tray" kept English because tray numbers are silkscreened on the printer.                                                                                       |
| `label.cut_line`                    | Cut line                                      | کٹ لائن                                  | Transliteration; alternative کٹائی کی لکیر. This is a screen-only marker (`no-print`), so it never reaches the physical label.                                                           |
| `label.print_mode`                  | DPI 203 · Direct Thermal                      | DPI 203 · ڈائریکٹ تھرمل                  | ڈائریکٹ تھرمل is what printer resellers in Lahore use; alternative: براہِ راست تھرمل.                                                                                                    |

## 2. Sentences where the Urdu is a rewrite, not a word-for-word conversion

| key                                               | English                                                                                                     | Urdu used                                                                                                             | Why unsure                                                                                                                                                                                                               |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `list.subtitle`                                   | Central specimen accessioning and chain of custody tracking                                                 | مرکزی سطح پر نمونوں کی accessioning اور chain of custody کی نگرانی                                                    | Keeps three English technical terms inside an Urdu frame. Reviewer should confirm this is how the lab describes the screen internally.                                                                                   |
| `collect.notes_placeholder`                       | e.g. Venipuncture completed on right antecubital fossa without hemolysis. Patient tolerated well.           | مثلاً: دائیں کہنی کے اندرونی حصے سے خون لیا گیا، کوئی hemolysis نہیں ہوا۔ مریض نے آسانی سے برداشت کیا۔                | antecubital fossa is rendered descriptively (کہنی کے اندرونی حصہ) instead of transliterated; hemolysis stays English because it is a clinical finding. Check a phlebotomist would write it this way.                     |
| `verify.all_ready_for_draw`                       | All specimens ready for draw                                                                                | تمام نمونے خون لینے کے لیے تیار                                                                                       | "draw" = خون لینا. Could also be نمونے لینے کے لیے تیار.                                                                                                                                                                 |
| `detail.event_timeline_desc`                      | Chronological chain of custody and status events (oldest first)                                             | تحویل اور حیثیت کے واقعات کی زمانی ترتیب (سب سے پرانا پہلے)                                                           | زمانی ترتیب is formal register; check it is not too literary for a technician.                                                                                                                                           |
| `detail.custody_sealed`                           | Chain of custody digitally sealed under ISO 15189 compliance                                                | chain of custody ISO 15189 کی تعمیل میں ڈیجیٹل طور پر محفوظ ہے                                                        | "sealed" rendered as محفوظ (protected/saved), not مہر بند, which would sound like a physical seal.                                                                                                                       |
| `detail.event_note_default`                       | Event recorded in specimen custody system.                                                                  | واقعہ نمونہ تحویل کے نظام میں درج ہو گیا۔                                                                             | Neutral; fine, but listed because "event" here is a custody event, not an incident.                                                                                                                                      |
| `detail.reject_desc_pre` + `reject_desc_post`     | Rejection permanently stops testing on this specimen and prompts a recollection request for patient {name}. | مسترد کرنے سے اس نمونے پر ٹیسٹنگ مستقل بند ہو جائے گی اور مریض {name} کے لیے دوبارہ نمونہ لینے کی درخواست بن جائے گی۔ | Split around the patient name so the name stays in its own LTR element. **`reject_desc_post` intentionally begins with a space** (Urdu needs "نام کے لیے"). Do not trim it.                                              |
| `detail.transfer_desc_pre` + `transfer_desc_post` | Dispatch accession {id} to another laboratory facility with cold-chain custody tracking.                    | accession {id} کو کولڈ چین تحویل کی ٹریکنگ کے ساتھ دوسری لیبارٹری سہولت میں بھیجیں۔                                   | Urdu pre-position puts the accession first, so `transfer_desc_pre` is just "accession" while English says "Dispatch accession". Both are correct in their own language, but reviewers should confirm the sentence order. |
| `detail.reject_reason_label`                      | Quality Non-Conformance Reason *                                                                            | معیار میں عدم مطابقت کی وجہ *                                                                                         | عدم مطابقت is QMS vocabulary; staff may say غیر مطابقت.                                                                                                                                                                  |
| `reject_reasons.clotted`                          | Clotted EDTA / micro-clots detected                                                                         | EDTA جم گیا یا چھوٹے لوتھڑے ملے                                                                                       | micro-clots rendered as چھوٹے لوتھڑے (small clots).                                                                                                                                                                      |
| `reject_reasons.hemolyzed`                        | Gross hemolysis detected on centrifugation                                                                  | سینٹری فیوج کرنے پر واضح hemolysis دیکھا گیا                                                                          | "gross hemolysis" — واضح ہے approx; the clinical term stays English.                                                                                                                                                     |
| `reject_reasons.mislabelled`                      | Mislabeled / unlabeled tube                                                                                 | ٹیوب پر لیبل غلط ہے یا لیبل نہیں لگا                                                                                  | Two conditions collapsed into one natural sentence.                                                                                                                                                                      |
| `toast.rejected_desc`                             | Accession {id} marked as rejected. Recollection flagged.                                                    | Accession {id} کو مسترد قرار دیا گیا۔ دوبارہ نمونہ لینے کی نشان دہی ہو گئی۔                                           | "flagged" has no clean Urdu; نشان دہی ہو گئی means "has been marked/indicated".                                                                                                                                          |
| `toast.transfer_desc`                             | Specimen transit record created for {id}.                                                                   | {id} کے لیے نمونہ ٹرانزٹ ریکارڈ بن گیا۔                                                                               | ٹرانزٹ transliterated.                                                                                                                                                                                                   |
| `label.reprint_logged`                            | Reprint #{{n}} audit logged under ISO 15189.                                                                | دوبارہ پرنٹ #{{n}} ISO 15189 کے تحت آڈٹ لاگ میں درج ہو گیا۔                                                           | The `#` and the digit stay Latin; sentence order changed to keep the number adjacent to its noun.                                                                                                                        |
| `label.print_dispatched_desc`                     | Print job dispatched to thermal printer for {id}.                                                           | {id} کے لیے تھرمل پرنٹر کو پرنٹ جاب بھیج دی گئی ہے۔                                                                   | پرنٹ جاب is feminine (جاب), hence بھیج دی گئی ہے.                                                                                                                                                                        |
| `detail.auto_dismiss`                             | Auto-dismiss in 5s                                                                                          | 5s میں خود بخود بند ہو جائے گا                                                                                        | Kept the Latin "s" suffix identical to the source; alternative: 5 سیکنڈ میں.                                                                                                                                             |
| `verify.auto_opening`                             | Auto-opening in {{seconds}}s                                                                                | {{seconds}}s میں خود بخود کھل جائے گا                                                                                 | Same "s" suffix decision as above; keep if reviewers accept it.                                                                                                                                                          |
| `actions.open_now`                                | Open now →                                                                                                  | ابھی کھولیں ←                                                                                                         | The **arrow is mirrored in the Urdu value** (→ becomes ←) because the UI runs RTL. This is the one place where the translation deliberately changes a glyph.                                                             |
| `collect.optional_paren` / `time.pkt_paren`       | (optional) / (PKT)                                                                                          | (اختیاری) / (PKT)                                                                                                     | Parentheses kept ASCII in both locales so the label wrapper does not break.                                                                                                                                              |
| `list.recent`                                     | Recent                                                                                                      | حالیہ                                                                                                                 | Shown when `age_display` is empty in the Age column; حالیہ reads as "recent" for a time, which fits.                                                                                                                     |

## 3. Latin data kept inside Urdu sentences (not translated, by design)

These values stay in Latin script and are rendered inside `<bdi dir="ltr">` or a
`dir="ltr"` element:

- accession IDs, MRNs, invoice numbers, patient names, branch names, clinician
  names, operator emails, station/bench/rack codes, phone numbers, dates,
  amounts, units, `ISO 15189`, `PKT`, `SHA-256: 7f83b165...041e`, `REF-…`.
- test names, panel names, tube additives (`EDTA`, `Fluoride Plasma`),
  specimen types, event types (`COLLECTED`), rejection reason codes.
- `Accession ID` table header and `Accession` prefix in the success toast keep
  the English word per GLOSSARY.md (accession is never translated).

**Terminology deviation worth a second look:** English "specimen" is rendered
with the glossary's word for sample, **نمونہ**, everywhere it is prose
(notes hint, transfer/reject titles, event note, label footer, toast). GLOSSARY.md
does not list "specimen", and اسپیسیمن appears nowhere in the repo's attested
Urdu; نمونہ is the word a Lahore laboratory actually writes. The only place a
Latin-ish compound survives is the invented bench caption (`نمونہ بینچ A`) and
the station/printer names, which are physical signage.

## 4. Things deliberately left English and NOT routed through i18n

1. **The printed 50 × 25 mm label** (`SampleLabelScreen`, inside
   `.printable-label`): barcode, accession ID, patient name, tests summary and
   the `Collected {datetime} · {branch}` caption. It is a physical object and
   must print exactly as recorded and LTR (Doc 07 §10 / task rule 5). Only the
   chrome around it (headings, metadata grid, buttons, toast, footer) is
   translated.
2. **`Code128Barcode.tsx`** — no visible text of its own (the optional `showText`
   renders the raw payload). Its `aria-label` is derived from the payload, so
   the file was not touched at all (band pattern bytes unchanged).
3. **`REF-` prefix and `SHA-256: …` footnote** on the detail screen: audit
   identifiers, not prose.

## 5. Behaviour notes for the reviewer (not Urdu questions)

- API error text now goes through `messageForError(err, t)` on all five screens
  (task rule 11). The old English fallbacks that were only shown when an
  `Error` had no usable code — "Failed to load samples list.", "Invoice not
  found.", "Failed to record specimen collection.", "Failed to load sample
  details", "Failed to receive sample", "Rejection failed", "Transfer failed",
  "Failed to load sample label" — therefore no longer exist as literals; the
  generic/`common:errors.*` message is shown instead. Say so if product wants
  screen-specific wording back (that would need new keys).
- `SampleDetailScreen` and `SampleLabelScreen` now use `formatDate` /
  `formatDateTime` from `lib/format.ts` (task rule 10). The previous code
  converted to `Asia/Karachi` with `toLocaleString`; the shared formatter reads
  the wall-clock fields of the wire string (its documented contract is that the
  API sends `+05:00`). Output is identical for `+05:00` payloads and identical
  for the 09:15Z test fixture's date, but a `Z`-suffixed timestamp around
  midnight PKT would now show the UTC date. Flag if the API is known to send
  `Z` timestamps.
- The event-timeline clock still uses `toLocaleTimeString("en-GB", … Asia/Karachi)`
  because `lib/format.ts` has no time-only formatter; only the `PKT` label was
  moved to `samples:time.pkt_abbr`.
- Toast descriptions are plain strings in state, so interpolated accession
  IDs/branch names cannot be wrapped in `<bdi>` there. They are pure Latin runs
  bounded by Urdu text, which the bidi algorithm orders correctly, but this is
  the one place where the `<bdi>` invariant is not literally applied.
- `loadSamples` / `loadDetail` / `loadLabel` now include `t` in their
  `useCallback` dependencies (required by exhaustive-deps once the error text is
  translated). A language switch therefore re-runs the fetch once.
- One pre-existing broken class on the timeline dot (`--start-6`) was fixed to
  `-start-6` while converting the surrounding line to logical utilities, so the
  dot aligns at the start edge in both directions.
