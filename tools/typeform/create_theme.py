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
