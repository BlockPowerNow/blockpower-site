# Block Power

The public website for Block Power — building power, one block at a time.

Block Power turns the most reliable voters on a street into the people who turn out
everyone else: real maps, trusted neighbors, measured results.

## Structure

`index.html` is a single self-contained page (no build step, no dependencies). Fonts load
from Google Fonts; everything else is inline.

## Local preview

```
python3 -m http.server 8000
# open http://localhost:8000/index.html
```

## Hosting

Served via GitHub Pages from the `main` branch.

## `/block` -- Block Power packet sign-up (2026-10-29, not yet live)

`block/index.html` embeds the Block Power sign-up Typeform, named by `FORM_ID`
at the top of its script. Until that is set the page says the sign-up isn't
open and gives an email address. The form, its spec and its verifier live in a
private repository, not here: this repo is public. Run the verifier on this page
before deploying it. The page copy has not been reviewed by counsel.
