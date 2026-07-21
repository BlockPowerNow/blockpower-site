"""Create the Strategy Pack form from form_payload.json."""

import json
import pathlib
import sys

from tf_api import api

HERE = pathlib.Path(__file__).parent
IDS_PATH = HERE / "form_ids.json"


def main() -> int:
    ids = json.loads(IDS_PATH.read_text())
    theme_id = ids["theme_id"]

    existing_id = ids.get("form_id")
    if existing_id and "--force" not in sys.argv:
        try:
            api("GET", f"/forms/{existing_id}")
        except RuntimeError as exc:
            if "HTTP 404" not in str(exc):
                raise
        else:
            print(f"refusing to create a duplicate: form_ids.json already has "
                  f"form_id {existing_id}, and that form still exists.")
            print("Delete it first, or re-run with --force to create a new one anyway.")
            return 1

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
