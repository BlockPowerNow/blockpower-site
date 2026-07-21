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
