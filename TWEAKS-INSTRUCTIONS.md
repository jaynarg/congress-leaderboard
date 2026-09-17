# Layout and feature tweaks, round 1

All four files replace what's in the repo root. Upload and Vercel redeploys.

## 1. Byline in the header

"119th Congress - legislative activity - by Jay Nargundkar" on all three pages. 
It stays visible at every width. On narrow screens the title takes its own line and the byline sits on the second line beside the methodology link, without its leading middle dot.
it visible there.

## 2. Axis title no longer collides with the percentage labels

The plot's left margin went from 46px to 64px, which gives the rotated title about 12px of
clearance from the widest label ("100%").

## 3. Stage tiles filter the bill list

On a member page, "Out of committee", "Passed a chamber", and "Became law" are now buttons.

- Click one to filter the list below to those bills.
- The selected tile gets a dark ring; click it again (or the Clear button that appears next
  to the bill count) to remove the filter.
- The count line reads "8 shown - reached out of committee".
- Because the stage counts are cumulative, the filter means "reached at least this stage",
  which matches the tile number exactly.
- A tile showing zero isn't clickable.
- Stage filters combine with "Bipartisan only".
- Switching to the Cosponsored tab clears the stage filter, since the tile counts describe
  sponsored bills only.
