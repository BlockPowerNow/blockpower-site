# Strategy Pack Typeform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dead "Get your Strategy Pack" link on blockpower.org with a Typeform that captures contact details, motivation, and how much of their block the person will cover.

**Architecture:** A brand-matched theme and the form itself are created in the Hub3 Typeform account via the Create API, driven by two committed Python scripts (create + verify) that read the token from 1Password at runtime. The site change is three lines of HTML in a single static file. Self-notification email is the one step the API cannot do and is configured in the Typeform UI.

**Tech Stack:** Typeform Create API v1, Python 3.11+ (stdlib only -- `urllib`, `json`, `subprocess`), 1Password CLI (`op`), static HTML, GitHub Pages.

## Global Constraints

- **Token source:** 1Password, vault `Dev`, item `Typeform API - Hub3 Account`, field `credential`. The copies in `~/.env~` are dead (403) -- never use them.
- **`blockpower-site` is a PUBLIC repo.** No token, no secret, no response data may be committed. Scripts read credentials at runtime only.
- **Never print a token value** to stdout, logs, or the transcript.
- **Target workspace:** `eTZb5R` (Hub3 default workspace).
- **Form display URL pattern:** `https://o4ltnhc1g3t.typeform.com/to/<FORM_ID>`. Read the real value from `_links.display` on the create response -- do not assume `form.typeform.com`.
- **Form copy is verbatim from the spec.** Double dashes (`--`), never em dashes. No banned AI words.
- **Site file:** `index.html` is a single self-contained file with no build step. Do not introduce one.
- **Low-vision first:** the page is 20px base, high contrast. Popup opens at `data-tf-size="100"` (full viewport), never a small modal.
- Spec: `docs/superpowers/specs/2026-07-21-strategy-pack-typeform-design.md`

## Spec deviations (approved refinements)

Two changes from the written spec, both made because the primary source contradicted it:

1. **State is a two-option `multiple_choice`, not a 50-state `dropdown`, and it comes BEFORE the address group.** Dropdown choices have no `ref`, so logic on them must match a string constant -- brittle. A two-choice field has refs and branches reliably. Placing it before the address group also means a non-NC person is never asked for a street address the org will never mail to. They still leave name, email, and motivation.
2. **Self-notification email is a UI step (Task 4).** Verified absent from the API: a real form object has no `notifications` key at top level or in `settings`.

## File Structure

| File | Responsibility |
|---|---|
| `tools/typeform/form_payload.json` | The complete form definition. Data, not code, so it can be diffed and re-applied. |
| `tools/typeform/theme_payload.json` | Brand theme colors. |
| `tools/typeform/tf_api.py` | Thin API client: reads token from 1Password, does GET/POST. Single responsibility. |
| `tools/typeform/create_form.py` | Creates theme + form from the payloads, writes the resulting IDs to `form_ids.json`. |
| `tools/typeform/verify_form.py` | Asserts the live form matches the spec. This is the test. |
| `tools/typeform/form_ids.json` | Created theme ID, form ID, display URL. Committed -- these are public identifiers, not secrets. |
| `index.html` | Site. One line changed, one script tag added. |

---

### Task 1: API client and verifier (the failing test)

**Files:**
- Create: `tools/typeform/tf_api.py`
- Create: `tools/typeform/verify_form.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `tf_api.get_token() -> str`, `tf_api.api(method: str, path: str, body: dict | None = None) -> dict`. `verify_form.py` is a CLI taking one argument, a form ID, exiting 0 on pass and 1 on failure.

- [ ] **Step 1: Write the API client**

Create `tools/typeform/tf_api.py`:

```python
"""Minimal Typeform API client. Reads the PAT from 1Password at runtime.

The tokens in ~/.env~ are dead (403 since 2026-05-22). 1Password is canonical.
Never print the token.
"""

import json
import subprocess
import urllib.error
import urllib.request

API_ROOT = "https://api.typeform.com"
OP_ITEM = "Typeform API - Hub3 Account"
OP_VAULT = "Dev"

_TOKEN: str | None = None


def get_token() -> str:
    """Read the Typeform PAT from 1Password, once per process.

    Cached deliberately: `op` is slow and can prompt for biometrics, so calling
    it per request would prompt repeatedly.
    Never log the return value.
    """
    global _TOKEN
    if _TOKEN is not None:
        return _TOKEN
    result = subprocess.run(
        ["op", "item", "get", OP_ITEM, "--vault", OP_VAULT,
         "--fields", "credential", "--reveal"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"1Password read failed (exit {result.returncode})")
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("1Password returned an empty credential")
    _TOKEN = token
    return _TOKEN


def api(method: str, path: str, body: dict | None = None) -> dict:
    """Call the Typeform API. Raises RuntimeError on non-2xx."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API_ROOT}{path}", data=data, method=method,
        headers={
            "Authorization": f"Bearer {get_token()}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:500]
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {path} -> connection failed: {exc.reason}") from exc
```

- [ ] **Step 2: Write the verifier**

Create `tools/typeform/verify_form.py`. This asserts every structural claim the spec makes:

```python
"""Verify the live Strategy Pack form matches the spec. Exits 1 on any mismatch."""

import sys

from tf_api import api

EXPECTED_FIELDS = [
    ("housing_type", "multiple_choice", True),
    ("doors_count", "multiple_choice", True),
    ("building_scope", "multiple_choice", True),
    ("why_motivation", "long_text", True),
    ("full_name", "short_text", True),
    ("email_address", "email", True),
    ("phone", "phone_number", False),
    ("in_north_carolina", "multiple_choice", True),
    ("mailing_address", "group", False),
]

EXPECTED_GROUP_FIELDS = [
    ("street", "short_text", True),
    ("unit", "short_text", False),
    ("city", "short_text", True),
    ("zip_code", "short_text", True),
]

EXPECTED_CHOICES = {
    "housing_type": ["choice_house", "choice_building"],
    "doors_count": ["doors_5", "doors_10", "doors_50"],
    "building_scope": ["floor_only", "whole_building"],
    "in_north_carolina": ["nc_yes", "nc_no"],
}

EXPECTED_ENDINGS = ["ty_nc", "ty_other"]

EXPECTED_LOGIC_REFS = ("housing_type", "doors_count", "in_north_carolina")


def fail(problems: list[str], message: str) -> None:
    problems.append(message)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_form.py <form_id>")
        return 1
    form_id = sys.argv[1]
    form = api("GET", f"/forms/{form_id}")
    problems: list[str] = []

    fields = form.get("fields", [])
    by_ref = {f["ref"]: f for f in fields}

    # Field presence, type, and required-ness
    for ref, ftype, required in EXPECTED_FIELDS:
        field = by_ref.get(ref)
        if field is None:
            fail(problems, f"missing field: {ref}")
            continue
        if field["type"] != ftype:
            fail(problems, f"{ref}: expected type {ftype}, got {field['type']}")
        actual_required = field.get("validations", {}).get("required", False)
        if actual_required != required:
            fail(problems, f"{ref}: expected required={required}, got {actual_required}")

    # Field ORDER -- contact details must come after the branch questions
    actual_order = [f["ref"] for f in fields]
    expected_order = [ref for ref, _, _ in EXPECTED_FIELDS]
    if actual_order != expected_order:
        fail(problems, f"field order wrong:\n  expected {expected_order}\n  got      {actual_order}")

    # Choice refs -- logic depends on these exact values
    for ref, choice_refs in EXPECTED_CHOICES.items():
        field = by_ref.get(ref)
        if field is None:
            continue
        actual = [c.get("ref") for c in field.get("properties", {}).get("choices", [])]
        if actual != choice_refs:
            fail(problems, f"{ref}: expected choices {choice_refs}, got {actual}")

    # Address group subfields
    group = by_ref.get("mailing_address")
    if group is not None:
        sub = group.get("properties", {}).get("fields", [])
        sub_by_ref = {f["ref"]: f for f in sub}
        for ref, ftype, required in EXPECTED_GROUP_FIELDS:
            field = sub_by_ref.get(ref)
            if field is None:
                fail(problems, f"missing address subfield: {ref}")
                continue
            if field["type"] != ftype:
                fail(problems, f"{ref}: expected type {ftype}, got {field['type']}")
            actual_required = field.get("validations", {}).get("required", False)
            if actual_required != required:
                fail(problems, f"{ref}: expected required={required}, got {actual_required}")
        if "state" in sub_by_ref:
            fail(problems, "address group must not ask for state -- NC is already known")

    # Exactly two endings, NC one first (first screen is the default fallthrough)
    endings = [t["ref"] for t in form.get("thankyou_screens", [])]
    if endings != EXPECTED_ENDINGS:
        fail(problems, f"expected exactly endings {EXPECTED_ENDINGS} in that order, got {endings}")

    # Logic: three rules, exactly -- no more, no fewer
    logic_by_ref = {rule["ref"]: rule for rule in form.get("logic", [])}
    for ref in EXPECTED_LOGIC_REFS:
        if ref not in logic_by_ref:
            fail(problems, f"missing logic rule on {ref}")
    unexpected_logic = [ref for ref in logic_by_ref if ref not in EXPECTED_LOGIC_REFS]
    if unexpected_logic:
        fail(problems, f"unexpected logic rule(s): {unexpected_logic}")
    if len(logic_by_ref) != len(EXPECTED_LOGIC_REFS):
        fail(
            problems,
            f"expected exactly {len(EXPECTED_LOGIC_REFS)} logic rules, "
            f"got {len(logic_by_ref)}: {sorted(logic_by_ref)}",
        )

    # Building path skips the doors question
    housing = logic_by_ref.get("housing_type")
    if housing:
        targets = [a["details"]["to"]["value"] for a in housing["actions"]]
        if "building_scope" not in targets:
            fail(problems, f"housing_type must jump to building_scope; targets={targets}")

    # House path skips the building question
    doors = logic_by_ref.get("doors_count")
    if doors:
        targets = [a["details"]["to"]["value"] for a in doors["actions"]]
        if "why_motivation" not in targets:
            fail(problems, f"doors_count must jump to why_motivation; targets={targets}")

    # Non-NC routes to the other ending
    nc = logic_by_ref.get("in_north_carolina")
    if nc:
        targets = [a["details"]["to"]["value"] for a in nc["actions"]]
        if "ty_other" not in targets:
            fail(problems, f"in_north_carolina must jump to ty_other; targets={targets}")

    # Copy rule: em dashes are banned in Karthik's prose
    blob = str(form)
    if "—" in blob:
        fail(problems, "form copy contains an em dash -- use double dashes")

    if problems:
        print(f"FAIL ({len(problems)} problems):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"PASS: form {form_id} matches spec")
    print(f"  display URL: {form['_links']['display']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run the verifier against a form that does not exist yet, to confirm it fails**

Run:
```bash
cd ~/repos/blockpower-site/tools/typeform && python3 verify_form.py NOSUCHFORM
```
Expected: non-zero exit, error text containing `HTTP 404`. This confirms the verifier actually calls the API and does not pass vacuously.

- [ ] **Step 4: Confirm the verifier catches a real structural mismatch**

Run it against an existing Hub3 form that is definitely not our form:
```bash
cd ~/repos/blockpower-site/tools/typeform && python3 verify_form.py sS3FFNdl
```
Expected: exit 1, `FAIL` with `missing field: housing_type` among the problems. A verifier that passes here is broken.

- [ ] **Step 5: Commit**

```bash
cd ~/repos/blockpower-site
git add tools/typeform/tf_api.py tools/typeform/verify_form.py
git commit -m "Add Typeform API client and Strategy Pack form verifier"
```

---

### Task 2: Theme

**Files:**
- Create: `tools/typeform/theme_payload.json`
- Create: `tools/typeform/create_theme.py`
- Modify: `tools/typeform/form_ids.json` (created here)

**Interfaces:**
- Consumes: `tf_api.api` from Task 1.
- Produces: `form_ids.json` containing key `theme_id` (string).

- [ ] **Step 1: Write the theme payload**

Colors are lifted from the site's CSS custom properties in `index.html` (`--paper`, `--ink`, `--power`, `--green`). Create `tools/typeform/theme_payload.json`:

```json
{
  "name": "Block Power",
  "colors": {
    "question": "#181410",
    "answer": "#15453a",
    "button": "#df3b29",
    "background": "#f6efe0"
  },
  "has_transparent_button": false
}
```

- [ ] **Step 2: Write the theme creation script**

Create `tools/typeform/create_theme.py`:

```python
"""Create the Block Power Typeform theme. Idempotent by name."""

import json
import pathlib

from tf_api import api

HERE = pathlib.Path(__file__).parent
IDS_PATH = HERE / "form_ids.json"


def main() -> int:
    payload = json.loads((HERE / "theme_payload.json").read_text())

    existing = api("GET", "/themes?page_size=200")
    for theme in existing.get("items", []):
        if theme.get("name") == payload["name"]:
            theme_id = theme["id"]
            print(f"theme already exists: {theme_id}")
            break
    else:
        created = api("POST", "/themes", payload)
        theme_id = created["id"]
        print(f"created theme: {theme_id}")

    ids = json.loads(IDS_PATH.read_text()) if IDS_PATH.exists() else {}
    ids["theme_id"] = theme_id
    IDS_PATH.write_text(json.dumps(ids, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run it**

```bash
cd ~/repos/blockpower-site/tools/typeform && python3 create_theme.py
```
Expected: `created theme: <id>` and `form_ids.json` now exists containing `theme_id`.

- [ ] **Step 4: Verify the theme came back with the colors we asked for**

```bash
cd ~/repos/blockpower-site/tools/typeform && python3 -c "
import json, pathlib
from tf_api import api
tid = json.loads(pathlib.Path('form_ids.json').read_text())['theme_id']
t = api('GET', f'/themes/{tid}')
print('name:', t['name'])
print('colors:', t['colors'])
assert t['colors']['button'].lower() == '#df3b29', t['colors']
assert t['colors']['background'].lower() == '#f6efe0', t['colors']
print('PASS')
"
```
Expected: prints the colors and `PASS`.

- [ ] **Step 5: Commit**

```bash
cd ~/repos/blockpower-site
git add tools/typeform/theme_payload.json tools/typeform/create_theme.py tools/typeform/form_ids.json
git commit -m "Add Block Power Typeform theme matching site palette"
```

---

### Task 3: Create the form

**Files:**
- Create: `tools/typeform/form_payload.json`
- Create: `tools/typeform/create_form.py`
- Modify: `tools/typeform/form_ids.json`

**Interfaces:**
- Consumes: `tf_api.api` (Task 1), `form_ids.json["theme_id"]` (Task 2).
- Produces: `form_ids.json` gains `form_id` (string) and `display_url` (string). `display_url` is what Task 5 puts in the `href`.

- [ ] **Step 1: Write the form payload**

Create `tools/typeform/form_payload.json`. Copy is verbatim from the spec. `THEME_ID_PLACEHOLDER` is substituted at runtime by the script in Step 2 -- it is not left in the sent payload.

```json
{
  "title": "Get your Strategy Pack",
  "type": "form",
  "workspace": { "href": "https://api.typeform.com/workspaces/eTZb5R" },
  "theme": { "href": "https://api.typeform.com/themes/THEME_ID_PLACEHOLDER" },
  "settings": {
    "language": "en",
    "is_public": true,
    "progress_bar": "proportion",
    "show_progress_bar": true,
    "show_typeform_branding": false,
    "meta": { "allow_indexing": false }
  },
  "welcome_screens": [
    {
      "ref": "welcome",
      "title": "Get your Strategy Pack",
      "properties": {
        "description": "You vote in every election. That makes you the right person to make sure your neighbors do too. Tell us where you are and how much of your block you want to cover, and we'll mail you a map of your precinct plus a one-page play.\n\nWe're organizing in North Carolina right now. About two minutes.",
        "show_button": true,
        "button_text": "Start"
      }
    }
  ],
  "fields": [
    {
      "ref": "housing_type",
      "title": "Where do you live?",
      "type": "multiple_choice",
      "validations": { "required": true },
      "properties": {
        "allow_multiple_selection": false,
        "allow_other_choice": false,
        "vertical_alignment": true,
        "choices": [
          { "ref": "choice_house", "label": "A house or townhouse on a street" },
          { "ref": "choice_building", "label": "An apartment or condo building" }
        ]
      }
    },
    {
      "ref": "doors_count",
      "title": "About how many doors can you cover?",
      "type": "multiple_choice",
      "validations": { "required": true },
      "properties": {
        "allow_multiple_selection": false,
        "allow_other_choice": false,
        "vertical_alignment": true,
        "choices": [
          { "ref": "doors_5", "label": "5 -- my closest neighbors" },
          { "ref": "doors_10", "label": "10 -- both sides of my street" },
          { "ref": "doors_50", "label": "50 -- my whole block" }
        ]
      }
    },
    {
      "ref": "building_scope",
      "title": "How much of your building?",
      "type": "multiple_choice",
      "validations": { "required": true },
      "properties": {
        "allow_multiple_selection": false,
        "allow_other_choice": false,
        "vertical_alignment": true,
        "choices": [
          { "ref": "floor_only", "label": "Just my floor" },
          { "ref": "whole_building", "label": "The entire building" }
        ]
      }
    },
    {
      "ref": "why_motivation",
      "title": "Why do you want to do this?",
      "type": "long_text",
      "validations": { "required": true },
      "properties": { "description": "A sentence or two is plenty." }
    },
    {
      "ref": "full_name",
      "title": "What's your name?",
      "type": "short_text",
      "validations": { "required": true },
      "properties": {}
    },
    {
      "ref": "email_address",
      "title": "Where should we email you?",
      "type": "email",
      "validations": { "required": true },
      "properties": { "description": "For your confirmation, and a heads-up when your pack ships." }
    },
    {
      "ref": "phone",
      "title": "Phone number",
      "type": "phone_number",
      "validations": { "required": false },
      "properties": {
        "description": "Optional. Only if you'd rather we call or text about your precinct.",
        "default_country_code": "US"
      }
    },
    {
      "ref": "in_north_carolina",
      "title": "Are you in North Carolina?",
      "type": "multiple_choice",
      "validations": { "required": true },
      "properties": {
        "description": "We're only organizing in North Carolina right now.",
        "allow_multiple_selection": false,
        "allow_other_choice": false,
        "vertical_alignment": true,
        "choices": [
          { "ref": "nc_yes", "label": "Yes, I'm in North Carolina" },
          { "ref": "nc_no", "label": "No, I'm somewhere else" }
        ]
      }
    },
    {
      "ref": "mailing_address",
      "title": "Where should we mail your pack?",
      "type": "group",
      "properties": {
        "description": "Your address is how we find your precinct. Your Strategy Pack is mailed by Hub3 Inc., a 501(c)(3) -- signing up here is not a contribution to Block Power. We never share your information with a campaign or party unless you authorize it.",
        "show_button": true,
        "button_text": "Send it",
        "fields": [
          {
            "ref": "street",
            "title": "Street address",
            "type": "short_text",
            "validations": { "required": true },
            "properties": {}
          },
          {
            "ref": "unit",
            "title": "Apartment or unit",
            "type": "short_text",
            "validations": { "required": false },
            "properties": {}
          },
          {
            "ref": "city",
            "title": "City",
            "type": "short_text",
            "validations": { "required": true },
            "properties": {}
          },
          {
            "ref": "zip_code",
            "title": "ZIP code",
            "type": "short_text",
            "validations": { "required": true },
            "properties": {}
          }
        ]
      }
    }
  ],
  "thankyou_screens": [
    {
      "ref": "ty_nc",
      "title": "Thanks -- we've got it.",
      "type": "thankyou_screen",
      "properties": {
        "description": "We'll build your precinct map and mail your Strategy Pack. Watch your email for a confirmation. If anything's wrong with your address, reply to it and we'll fix it.",
        "show_button": false,
        "share_icons": false
      }
    },
    {
      "ref": "ty_other",
      "title": "Thanks for signing up.",
      "type": "thankyou_screen",
      "properties": {
        "description": "We're only organizing in North Carolina right now, so we can't build your precinct map yet. We'll hold your details and email you when we reach your state.",
        "show_button": false,
        "share_icons": false
      }
    }
  ],
  "logic": [
    {
      "type": "field",
      "ref": "housing_type",
      "actions": [
        {
          "action": "jump",
          "condition": {
            "op": "is",
            "vars": [
              { "type": "field", "value": "housing_type" },
              { "type": "choice", "value": "choice_building" }
            ]
          },
          "details": { "to": { "type": "field", "value": "building_scope" } }
        }
      ]
    },
    {
      "type": "field",
      "ref": "doors_count",
      "actions": [
        {
          "action": "jump",
          "condition": { "op": "always", "vars": [] },
          "details": { "to": { "type": "field", "value": "why_motivation" } }
        }
      ]
    },
    {
      "type": "field",
      "ref": "in_north_carolina",
      "actions": [
        {
          "action": "jump",
          "condition": {
            "op": "is",
            "vars": [
              { "type": "field", "value": "in_north_carolina" },
              { "type": "choice", "value": "nc_no" }
            ]
          },
          "details": { "to": { "type": "thankyou", "value": "ty_other" } }
        }
      ]
    }
  ]
}
```

- [ ] **Step 2: Write the creation script**

Create `tools/typeform/create_form.py`:

```python
"""Create the Strategy Pack form from form_payload.json."""

import json
import pathlib

from tf_api import api

HERE = pathlib.Path(__file__).parent
IDS_PATH = HERE / "form_ids.json"


def main() -> int:
    ids = json.loads(IDS_PATH.read_text())
    theme_id = ids["theme_id"]

    raw = (HERE / "form_payload.json").read_text()
    payload = json.loads(raw.replace("THEME_ID_PLACEHOLDER", theme_id))

    if "THEME_ID_PLACEHOLDER" in json.dumps(payload):
        raise RuntimeError("theme placeholder was not substituted")

    created = api("POST", "/forms", payload)
    ids["form_id"] = created["id"]
    ids["display_url"] = created["_links"]["display"]
    IDS_PATH.write_text(json.dumps(ids, indent=2) + "\n")

    print(f"created form: {created['id']}")
    print(f"display URL:  {created['_links']['display']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Create the form**

```bash
cd ~/repos/blockpower-site/tools/typeform && python3 create_form.py
```
Expected: `created form: <id>` and a display URL on the `o4ltnhc1g3t.typeform.com` subdomain.

If this returns HTTP 400, the error body names the offending field path. Fix `form_payload.json` and re-run -- do not patch the created form by hand, or the payload stops being the source of truth.

- [ ] **Step 4: Run the verifier -- it must now pass**

```bash
cd ~/repos/blockpower-site/tools/typeform && python3 verify_form.py "$(python3 -c "import json;print(json.load(open('form_ids.json'))['form_id'])")"
```
Expected: `PASS: form <id> matches spec` and exit 0. This is the same script that failed in Task 1 Step 4.

- [ ] **Step 5: Walk both branches by hand in a browser**

Open the display URL. Confirm:
- Choosing "A house or townhouse on a street" shows the 5/10/50 doors question and never shows the building question.
- Choosing "An apartment or condo building" shows floor/entire-building and never shows the doors question.
- Answering "No, I'm somewhere else" ends the form immediately without asking for a street address.

The verifier checks that the logic rules exist and point at the right targets; it cannot confirm Typeform evaluates them the way we expect. Do not skip this step.

- [ ] **Step 6: Commit**

```bash
cd ~/repos/blockpower-site
git add tools/typeform/form_payload.json tools/typeform/create_form.py tools/typeform/form_ids.json
git commit -m "Create Strategy Pack form via Typeform API"
```

---

### Task 4: Self-notification email

**Files:**
- Modify: `docs/superpowers/specs/2026-07-21-strategy-pack-typeform-design.md` (record that this is a UI step)

**Interfaces:**
- Consumes: `form_ids.json["form_id"]` (Task 3).
- Produces: nothing consumed by later tasks.

This is the one step with no API. Verified: a real form object has no `notifications` key at top level or inside `settings`.

- [ ] **Step 1: Configure the notification in the Typeform UI**

Open the form in the Typeform editor as `karthik@hub3.us`. Go to **Connect -> Notifications -> Self notifications**. Enable it. Set the recipient to `karthik@hub3.us`. Set the subject to `Strategy Pack signup`. Include all fields in the body.

- [ ] **Step 2: Submit a North Carolina test response**

Use the display URL. Answer: house, 50 doors, any motivation text, name `TEST -- delete me`, email `karthik@hub3.us`, skip phone, "Yes, I'm in North Carolina", any NC address.

Expected: ending A -- "Thanks -- we've got it."

- [ ] **Step 3: Confirm the notification email actually arrived**

Check the `karthik@hub3.us` inbox for the notification.

A saved setting is not a delivered email. Do not mark this task done on the strength of the toggle being on -- confirm the message is in the inbox. If it has not arrived within five minutes, check spam, then re-check the recipient address in the UI.

- [ ] **Step 4: Submit a non-NC test response**

Answer: apartment building, entire building, any motivation, name `TEST 2 -- delete me`, email `karthik@hub3.us`, "No, I'm somewhere else".

Expected: the form ends immediately at ending B -- "Thanks for signing up." -- and never asks for a street address.

- [ ] **Step 5: Record the UI dependency in the spec**

Append to the "Out of scope" section of `docs/superpowers/specs/2026-07-21-strategy-pack-typeform-design.md`:

```markdown
- Self-notification email is configured in the Typeform UI, not in code. It is
  not covered by `verify_form.py` and will not survive a form rebuild from
  `form_payload.json`. If the form is ever recreated, re-do Task 4.
```

- [ ] **Step 6: Commit**

```bash
cd ~/repos/blockpower-site
git add docs/superpowers/specs/2026-07-21-strategy-pack-typeform-design.md
git commit -m "Note that self-notification email is a UI step, not API-managed"
```

---

### Task 5: Wire the embed into the site

**Files:**
- Modify: `index.html` (line 435, and before the closing `</body>`)

**Interfaces:**
- Consumes: `form_ids.json["form_id"]` and `["display_url"]` (Task 3).
- Produces: the deployed site change.

- [ ] **Step 1: Confirm the exact current state of the line**

```bash
cd ~/repos/blockpower-site && grep -n "husb.link/myblock" index.html
```
Expected: exactly one match, on line 435. If there is more than one, every occurrence must be replaced -- adjust the following steps accordingly.

- [ ] **Step 2: Replace the dead link**

Substituting the real form ID and display URL from `tools/typeform/form_ids.json`, change line 435 from:

```html
        <a class="btn" href="https://husb.link/myblock" target="_blank" rel="noopener">Get your Strategy Pack <span class="arrow">→</span></a>
```

to:

```html
        <a class="btn" href="DISPLAY_URL_FROM_form_ids.json" data-tf-popup="FORM_ID_FROM_form_ids.json" data-tf-size="100" target="_blank" rel="noopener">Get your Strategy Pack <span class="arrow">→</span></a>
```

The `href` stays a real, working URL on purpose. If the Typeform script is blocked or fails to load, the button opens the hosted form in a new tab. A button that silently does nothing is the exact bug this whole change exists to fix.

Leave the `<span class="arrow">` and its `→` character alone. That is page markup, not prose, and the em-dash/arrow rule does not apply to it.

- [ ] **Step 3: Add the embed script**

Immediately before the closing `</body>` tag, add:

```html
<script src="//embed.typeform.com/next/embed.js"></script>
```

- [ ] **Step 4: Verify no dead link remains**

```bash
cd ~/repos/blockpower-site
grep -c "husb.link" index.html
```
Expected: `0`.

```bash
grep -c "embed.typeform.com" index.html
```
Expected: `1`.

- [ ] **Step 5: Test locally, including the failure mode**

```bash
cd ~/repos/blockpower-site && python3 -m http.server 8731
```

Open `http://localhost:8731/index.html` and confirm:
1. The page renders exactly as before -- nothing shifted.
2. Clicking "Get your Strategy Pack" opens the form as a full-viewport overlay.
3. In devtools, block `embed.typeform.com`, hard-reload, and click the button again. It must open the hosted form in a new tab rather than doing nothing.

Stop the server when done.

- [ ] **Step 6: Commit**

```bash
cd ~/repos/blockpower-site
git add index.html
git commit -m "Replace dead Strategy Pack link with Typeform popup

husb.link/myblock 302s to Rebrandly's broken-links page, so the site's
primary CTA went nowhere. The href is a working form URL underneath the
popup attribute, so a blocked embed script degrades to a new tab rather
than a dead button."
```

---

### Task 6: Deploy and verify in production

**Files:**
- No new files. Pushes `strategy-pack-form` and merges to `main`.

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Push the branch**

```bash
cd ~/repos/blockpower-site && git push -u origin strategy-pack-form
```

- [ ] **Step 2: Merge to main**

GitHub Pages serves `main` at root. Karthik decides PR vs direct merge -- ask before merging, since this publishes to a live public site.

```bash
cd ~/repos/blockpower-site
git checkout main && git merge --ff-only strategy-pack-form && git push origin main
```

- [ ] **Step 3: Wait for Pages to rebuild, then confirm the deploy landed**

```bash
sleep 90
curl -s https://blockpower.org | grep -c "husb.link"
```
Expected: `0`.

```bash
curl -s https://blockpower.org | grep -c "embed.typeform.com"
```
Expected: `1`.

- [ ] **Step 4: Test the live button**

Load `https://blockpower.org`, click "Get your Strategy Pack", confirm the popup opens.

- [ ] **Step 5: Submit one live end-to-end test and confirm the notification**

Submit a real NC response through the production page. Confirm it appears in Typeform responses AND that the notification email reaches `karthik@hub3.us`.

- [ ] **Step 6: Delete all test responses**

In the Typeform responses view, delete every response whose name starts with `TEST`. Confirm the response count is 0 before calling this done.

- [ ] **Step 7: Verify the count is actually zero**

```bash
cd ~/repos/blockpower-site/tools/typeform && python3 -c "
import json, pathlib
from tf_api import api
fid = json.loads(pathlib.Path('form_ids.json').read_text())['form_id']
r = api('GET', f'/forms/{fid}/responses?page_size=1')
print('remaining responses:', r['total_items'])
assert r['total_items'] == 0, 'test responses still present'
print('PASS')
"
```
Expected: `remaining responses: 0` and `PASS`.

---

## Follow-ups this plan does NOT do

Named so they are not mistaken for done. None of these are tracked yet.

- **Privacy and Terms are still `#` stubs** in the footer while the form now collects home addresses. The footer already promises "We never share your information with a campaign or party unless you authorize it" with no policy behind it.
- **Nobody is named to print the maps and mail the packs.** The form promises a mailed pack; Karthik is in NL from June.
- **`husb.link/myblock` stays broken** for anyone holding the old link. Repoint it at the new form via the Rebrandly API.
- **The three dead Typeform tokens in `~/.env~`** should be removed or refreshed so the next session does not repeat the May dead end.
