# Attribution

The following top-level skills are vendored from Anthropic's open-source
[`anthropics/financial-services`](https://github.com/anthropics/financial-services)
repository, licensed under **Apache License 2.0** (see `LICENSE.anthropic-skills`).

- Source commit: `4aa51ed3d379731f8f9beff498d749580372699c` (2026-06-26)
- Imported: 2026-07-02

Only skills that carry **no external-data dependency** were vendored — they operate
purely on user-supplied inputs, logic, or formatting (no SEC/EDGAR, market-data,
or enterprise-system connectors). They sit as siblings to the repo's own `data/`
and `backtesting/` skills.

## Vendored skills (21)

**Output / check engines**
`xlsx-author`, `pptx-author`, `audit-xls`, `clean-data-xls`,
`ib-check-deck`, `deck-refresh`

**Model math**
`lbo-model`, `merger-model`, `returns-analysis`, `unit-economics`

**Document drafting / process**
`ic-memo`, `teaser`, `process-letter`, `cim-builder`, `dd-checklist`,
`dd-meeting-prep`, `deal-screening`, `deal-tracker`, `investment-proposal`,
`kyc-doc-parse`, `kyc-rules`

Each was taken from the richest copy present in the source repo's `plugins/` tree
(a single skill can appear in multiple plugins). Skill contents are unmodified
except for the local additions below.

## Not vendored (meta-skills, deliberately excluded)

`skill-creator` and `ppt-template-creator` were dropped — both are meta-skills for
*authoring skills*, not financial capabilities, and `ppt-template-creator` depended
on `skill-creator`.

## Local additions / modifications

The source repo referenced a few runtime assets it never actually shipped. Supplied
locally so the vendored skills resolve standalone:

- `lbo-model/scripts/recalc.py` — LibreOffice-headless formula recalc helper,
  replacing the source's `/mnt/skills/public/xlsx/recalc.py` sandbox path (the
  reference in `lbo-model/SKILL.md` was repointed to `scripts/recalc.py`).
- `lbo-model/examples/LBO_Model.xlsx` — standard LBO template skeleton
  (Assumptions · Sources & Uses · Operating Model · Debt Schedule · Returns ·
  Checks), formula-driven per the skill's blue/black/green conventions. The source
  referenced this template but did not include it.

`pptx-author`'s optional `templates/firm-template.pptx` is intentionally not
supplied — the skill already falls back to default layouts when no template is
mounted.
