# Patch: summary ordering, prompt, and a regenerate switch

## Files (both replace what's in the repo)

- `pipeline/summarize.py`
- `.github/workflows/update-data.yml`

## What changed

1. **Oldest bills first.** The queue now runs oldest-to-newest within each bill type. The
   first run looked at the newest bills, where Congress.gov often hasn't published text
   yet, which is why 109 of 209 came back with nothing to summarize.
2. **Prompt leads with the verb.** "Authorizes grants to..." instead of "The bill
   authorizes...". Telling the model what to do works better than telling it what to
   avoid. Word cap tightened from 45 to 40.
3. **New regenerate switch.** No need to delete any files. The Run workflow dropdown now
   has a **"Rewrite summaries that already exist"** checkbox. It never overwrites a
   Congressional Research Service summary.

## To rewrite the 98 existing summaries

Actions -> Update Congress data -> Run workflow, tick **Rewrite summaries that already
exist**, and put `120` in the summary limit field so it stops after the existing ones plus
a few. Cost is around ten cents.

Then leave both fields alone for the full backfill. Real cost is running about $0.00094 per
summary, so all 11,410 should come to roughly $11.
