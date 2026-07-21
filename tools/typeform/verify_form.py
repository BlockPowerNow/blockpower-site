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
