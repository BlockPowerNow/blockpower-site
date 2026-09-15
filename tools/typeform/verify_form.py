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
    # Address is four STANDALONE fields, deliberately not a `group`. Typeform
    # does not enforce validations.required on subfields inside a group -- a
    # live submission got through with the entire address empty, while the API
    # still reported required=True on each subfield. Standalone fields enforce.
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

# Typeform injects its own "default_tys" fallback ending on every form --
# the unrelated production form sS3FFNdl carries one too. It cannot be
# suppressed via the Create API, so we assert it exactly rather than
# ignoring extras: any OTHER stray ending still fails.
EXPECTED_ENDINGS = ["ty_nc", "ty_other", "default_tys"]

EXPECTED_LOGIC_REFS = (
    "housing_type",
    "doors_count",
    "in_north_carolina",
    # Terminates the NC path explicitly on the LAST address question. Without
    # it Typeform routes to its own "default_tys" ending with generic copy.
    "zip_code",
)


def fail(problems: list[str], message: str) -> None:
    problems.append(message)


def _is_choice_condition(condition: dict, field_ref: str, choice_ref: str) -> bool:
    """True if condition is `field_ref is choice_ref`."""
    if condition.get("op") != "is":
        return False
    field_var, choice_var = (condition.get("vars") or [{}, {}])[:2] or ({}, {})
    return (
        field_var.get("type") == "field" and field_var.get("value") == field_ref
        and choice_var.get("type") == "choice" and choice_var.get("value") == choice_ref
    )


def _is_always_condition(condition: dict) -> bool:
    return condition.get("op") == "always"


def _find_action(actions: list[dict], predicate) -> dict | None:
    """Return the first action whose condition satisfies predicate, or None.

    Matching the target alone is not enough -- a rule that jumps to the right
    place on the WRONG condition would still look correct if only the target
    were checked. Find the action by its condition first, then check where it
    goes.
    """
    for action in actions:
        if predicate(action.get("condition", {})):
            return action
    return None


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

    # The address must NOT be a question group -- required is unenforced inside
    # one, which let a live submission through with no address at all.
    for field in fields:
        if field.get("type") == "group":
            fail(problems, f"field {field['ref']} is a group; address fields must be standalone")
    if "state" in by_ref:
        fail(problems, "must not ask for state -- NC is already known")

    # Hidden field: the postcard QR passes #invite_id=<code> so a sign-up links
    # back to the invited voter without matching on name and address.
    if form.get("hidden") != ["invite_id"]:
        fail(problems, f"hidden must be ['invite_id'], got {form.get('hidden')}")

    # Settings the form must ship with
    if form.get("settings", {}).get("is_public") is not True:
        fail(problems, f"settings.is_public must be true, got {form.get('settings', {}).get('is_public')}")
    theme_href = form.get("theme", {}).get("href", "")
    if not theme_href.endswith("yOsTRgUW"):
        fail(problems, f"theme href must end with yOsTRgUW, got {theme_href!r}")

    # Exactly three endings (NC, other, and Typeform's own default_tys),
    # NC one first (first screen is the default fallthrough)
    endings = [t["ref"] for t in form.get("thankyou_screens", [])]
    if endings != EXPECTED_ENDINGS:
        fail(problems, f"expected exactly endings {EXPECTED_ENDINGS} in that order, got {endings}")

    # Logic: four rules, exactly -- no more, no fewer
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

    # Building path skips the doors question -- jump must fire ON choice_building
    housing = logic_by_ref.get("housing_type")
    if housing:
        action = _find_action(
            housing["actions"], lambda c: _is_choice_condition(c, "housing_type", "choice_building")
        )
        if action is None:
            fail(problems, f"housing_type must jump to building_scope when choice_building is picked; actions={housing['actions']}")
        elif action["details"]["to"]["value"] != "building_scope":
            fail(problems, f"housing_type/choice_building must jump to building_scope, got {action['details']['to']['value']}")

    # House path skips the building question -- jump is unconditional
    doors = logic_by_ref.get("doors_count")
    if doors:
        action = _find_action(doors["actions"], _is_always_condition)
        if action is None:
            fail(problems, f"doors_count must jump to why_motivation unconditionally (op=always); actions={doors['actions']}")
        elif action["details"]["to"]["value"] != "why_motivation":
            fail(problems, f"doors_count's unconditional jump must target why_motivation, got {action['details']['to']['value']}")

    # Non-NC routes to the other ending -- jump must fire ON nc_no
    nc = logic_by_ref.get("in_north_carolina")
    if nc:
        action = _find_action(
            nc["actions"], lambda c: _is_choice_condition(c, "in_north_carolina", "nc_no")
        )
        if action is None:
            fail(problems, f"in_north_carolina must jump to ty_other when nc_no is picked; actions={nc['actions']}")
        elif action["details"]["to"]["value"] != "ty_other":
            fail(problems, f"in_north_carolina/nc_no must jump to ty_other, got {action['details']['to']['value']}")

    # NC path terminates on the last address question -- jump is unconditional
    zip_rule = logic_by_ref.get("zip_code")
    if zip_rule:
        action = _find_action(zip_rule["actions"], _is_always_condition)
        if action is None:
            fail(problems, f"zip_code must jump to ty_nc unconditionally (op=always); actions={zip_rule['actions']}")
        elif action["details"]["to"]["value"] != "ty_nc":
            fail(problems, f"zip_code's unconditional jump must target ty_nc, got {action['details']['to']['value']}")

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
