# SoundDue — Input Schema Reference

> **Prototype note:** SoundDue never claims royalties, decides ownership
> disputes, or implies that any amount is owed. All findings are produced for
> human review only.

---

## Why recordings and works are separate

A **recording** (phonogram) is a specific audio capture — the MP3 or WAV that
a distributor delivers. A **work** (musical composition) is the underlying
song — the melody and lyrics that writers and publishers administer.

One work can have many recordings (studio version, live version, radio edit,
cover by a different artist). Conversely, one recording can only correspond to
one primary work, but that link must be established by an explicit mapping from
an authoritative source.

**SoundDue never infers a recording ↔ work link from a title match alone.**
Doing so would be a category error: "Perfect" by Ed Sheeran and "Perfect" by
another artist are different works; a fuzzy title match cannot distinguish
them. Every link in the system must come from a `Mapping` row supplied in your
data files.

---

## Input file types

| File type | Purpose |
|-----------|---------|
| `recordings` | Sound recordings (phonograms) |
| `works` | Musical compositions |
| `mappings` | Explicit recording ↔ work links |
| `ownership` | Rights-holder share claims per work |

---

## 1. Recordings file

Each row describes one sound recording.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `recording_id` | string | **Yes** | Unique identifier for this recording in your system. Must not be blank. |
| `title` | string | **Yes** | Title of the recording. Must not be blank. |
| `performer` | string | No | Performing artist or group name. |
| `version` | string | No | Version label, e.g. `Radio Edit`, `Acoustic`. |
| `duration_seconds` | integer ≥ 0 | No | Track length in whole seconds. |
| `isrc` | string | No | 12-character ISRC (`CC-XXX-YY-NNNNN`, letters and digits). |

**Accepted header synonyms**

| Canonical field | Also accepted as … |
|-----------------|-------------------|
| `recording_id` | `Track Code`, `Track ID`, `Recording Code`, `Rec ID`, `rec_id`, `track_id` |
| `title` | `Track Title`, `Recording Title`, `Name` |
| `performer` | `Artist`, `Main Artist`, `Performer Name`, `artist_name` |
| `version` | `Mix`, `Version Label`, `Edit` |
| `duration_seconds` | `Duration`, `Length`, `Duration (s)`, `Secs`, `duration_secs` |
| `isrc` | `ISRC Code`, `ISRC Number`, `isrc_code` |

**Example row**

```csv
recording_id,title,performer,version,duration_seconds,isrc
USRC17607839,Shape of You,Ed Sheeran,Album Version,234,USRC17607839
```

---

## 2. Works file

Each row describes one musical composition.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `work_id` | string | **Yes** | Unique identifier for this work in your system. Must not be blank. |
| `title` | string | **Yes** | Title of the work. Must not be blank. |
| `writers` | string or list | No | Comma-separated list of composer/lyricist names. |
| `iswc` | string | No | ISWC in `T-XXXXXXXXX-C` format. |

**Accepted header synonyms**

| Canonical field | Also accepted as … |
|-----------------|-------------------|
| `work_id` | `Work Code`, `Composition ID`, `Song ID`, `work_code` |
| `title` | `Work Title`, `Song Title`, `Composition Title` |
| `writers` | `Composers`, `Songwriters`, `Authors`, `Writer Names`, `songwriter_names` |
| `iswc` | `ISWC Code`, `ISWC Number`, `iswc_code` |

**Example row**

```csv
work_id,title,writers,iswc
W-001,Shape of You,Ed Sheeran,T-034524680-1
```

---

## 3. Mappings file

Each row is an explicit, source-supplied link between a recording and a work.

> **Important:** A title match alone never constitutes a mapping. Only rows
> in this file (supplied by an authoritative source) create recording ↔ work
> links in SoundDue.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `recording_id` | string | **Yes** | Must match a `recording_id` in the recordings file. |
| `work_id` | string | **Yes** | Must match a `work_id` in the works file. |
| `source_label` | string | No | Name of the organisation supplying this mapping (e.g. `Sony`, `ASCAP`). |
| `verified` | boolean | No | `true` only if the source explicitly marks this link as verified. Defaults to `false`. |

**Accepted header synonyms**

| Canonical field | Also accepted as … |
|-----------------|-------------------|
| `recording_id` | `Track Code`, `Track ID`, `rec_id` |
| `work_id` | `Work Code`, `Composition ID`, `work_code` |
| `source_label` | `Source`, `Label`, `Supplied By`, `Data Source` |
| `verified` | `Confirmed`, `Verified Link`, `is_verified` |

**Example row**

```csv
recording_id,work_id,source_label,verified
USRC17607839,W-001,Sony,true
```

---

## 4. Ownership file

Each row is a single share claim from one rights holder for one work.

> **Share arithmetic warning:** Shares are stored as `Decimal`, not `float`,
> to avoid rounding errors. Use string values like `"33.3333"` when precision
> matters. Values like `"50.0"` or `"100"` are fine.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `work_id` | string | **Yes** | References the work this claim applies to. |
| `contributor_id` | string | **Yes** | Unique identifier for the rights holder. Must not be blank. |
| `contributor_name` | string | **Yes** | Human-readable name of the rights holder. Must not be blank. |
| `share` | Decimal 0–100 | **Yes** | Ownership share as a percentage. Must be > 0 and ≤ 100. **Not a float.** |
| `share_convention` | string | **Yes** | Convention used, e.g. `publisher-share`, `writer-share`, `100-percent-scale`. Shares in different conventions **cannot** be added together. |
| `rights_category` | string | **Yes** | Rights type, e.g. `mechanical`, `performance`, `sync`. |
| `territory` | string | **Yes** | Territory code, e.g. `WW` (worldwide), `US`, `GB`. |
| `effective_from` | date (YYYY-MM-DD) | **Yes** | Start of claim period (inclusive). |
| `effective_to` | date (YYYY-MM-DD) | **Yes** | End of claim period (inclusive). Must not be before `effective_from`. |
| `status` | enum | **Yes** | One of: `claimed`, `unclaimed`, `disputed`, `pending`, `unknown`. See note below. |

**Status vocabulary**

| Value | Meaning |
|-------|---------|
| `claimed` | The rights holder actively asserts this share. |
| `unclaimed` | The source file *explicitly* marks this share as unclaimed. **Do not use this if the share is merely absent from the data** — absent data means "missing from the supplied records". |
| `disputed` | Two or more parties claim conflicting rights to this share. |
| `pending` | The claim has been submitted but not yet confirmed. |
| `unknown` | The status cannot be determined from the available information. |

**Accepted header synonyms**

| Canonical field | Also accepted as … |
|-----------------|-------------------|
| `work_id` | `Work Code`, `Composition ID`, `work_code` |
| `contributor_id` | `Publisher ID`, `Writer ID`, `RH Code`, `rights_holder_id` |
| `contributor_name` | `Publisher`, `Writer`, `Rights Holder`, `rights_holder` |
| `share` | `Songwriter %`, `Publisher %`, `Share %`, `Ownership %`, `share_pct`, `pct` |
| `share_convention` | `Convention`, `Share Type`, `Scale`, `share_type` |
| `rights_category` | `Rights Type`, `Category`, `Right Type`, `rights_type` |
| `territory` | `Territory Code`, `Region`, `Market`, `territory_code` |
| `effective_from` | `Start Date`, `From`, `Period Start`, `period_start`, `from_date` |
| `effective_to` | `End Date`, `To`, `Period End`, `period_end`, `to_date` |
| `status` | `Claim Status`, `Share Status`, `claim_status` |

**Example rows**

```csv
work_id,contributor_id,contributor_name,share,share_convention,rights_category,territory,effective_from,effective_to,status
W-001,PUB-001,Sony Music Publishing,40.0000,publisher-share,mechanical,WW,2020-01-01,2025-12-31,claimed
W-001,WRT-001,Ed Sheeran,60.0000,publisher-share,mechanical,WW,2020-01-01,2025-12-31,claimed
W-002,WRT-001,Ed Sheeran,50.0000,publisher-share,performance,WW,2020-01-01,2025-12-31,claimed
```

> **Note on the third row:** `W-002` performance/WW only sums to 50% — this
> will trigger **RULE-001** (share gap). The remaining 50% is described as
> *"missing from the supplied records"*, not "unclaimed", because no source
> has explicitly labelled it unclaimed.

---

## Validation rules enforced on ingest

| Rule | Field(s) | Message |
|------|----------|---------|
| Non-empty ID | `recording_id`, `work_id`, `contributor_id` | `"… must not be empty or whitespace-only"` |
| Share range | `share` | `"share must be > 0 and ≤ 100"` |
| Share type | `share` | Must be parseable as Decimal; floats are coerced |
| Date order | `effective_from`, `effective_to` | `"effective_to must not be before effective_from"` |
| Status vocabulary | `status` | Must be one of `claimed`, `unclaimed`, `disputed`, `pending`, `unknown` |
| ISRC pattern | `isrc` | Must match `^[A-Z]{2}[A-Z0-9]{3}\d{7}$` |
| ISWC pattern | `iswc` | Must match `^T-\d{9}-\d$` |

---

## SourceRef — provenance

Every ingested row carries a `SourceRef` that is embedded in all findings and
evidence:

| Field | Type | Description |
|-------|------|-------------|
| `file_name` | string | Original upload file name |
| `row_number` | integer ≥ 1 | 1-based row number in the file |
| `raw_values` | dict | The original cell values before any normalisation |

This ensures every finding can be traced back to the exact file and row that
produced it.
