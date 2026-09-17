# Phase 4: the site (with the Vercel fix)

## 1. Move requirements.txt into the pipeline folder

Vercel saw `requirements.txt` at the repo root and assumed the project was a Python web
app, so it went looking for a server to run and failed. Moving the file removes that signal.
The nightly workflow still installs from it.

In GitHub: open `requirements.txt` -> pencil icon -> change the filename box to read
`pipeline/requirements.txt` -> commit.

## 2. Point the workflow at the new location

Open `.github/workflows/update-data.yml`, find this line:

    - run: pip install -r requirements.txt

and change it to:

    - run: pip install -r pipeline/requirements.txt

Commit.

## 3. Upload these files to the repo root

- `index.html`, `member.html`, `methodology.html`, `shared.css`
- `vercel.json` — tells Vercel there is nothing to build
- `.vercelignore` — keeps ~19,000 raw data files out of the deploy

## 4. Redeploy

In Vercel, open the project and start a new deployment of the latest commit. If the project
still has a framework preset set, change it to Other; `vercel.json` handles the rest.

## What to check once it's live

- The chart shows a few hundred marks; hovering one names the member.
- Typing a name filters the table; typing a state code (NJ) filters to that delegation.
- Clicking a member name opens their page with bills and stage badges.
- Most bills say "Summary pending" — that is Phase 2's job.

## Then confirm the pipeline still runs

Run the workflow once from the Actions tab and make sure the "Run pip install" step passes
with the new path.
