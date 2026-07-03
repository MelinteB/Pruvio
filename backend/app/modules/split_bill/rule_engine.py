import json
import re

MEASUREMENT_FRAGMENT_PATTERN = re.compile(
    r"\b(?P<value>(?=[0-9Oo]*[0-9])[0-9Oo]{1,6})\s*(?P<unit>GR|G|KG|ML|L|CL|DL)\b",
    re.IGNORECASE
)


def normalize_measurement_fragments(text: str) -> str:
    """
    Fixes OCR mistakes inside weight/volume fragments.

    Examples:
    2OOGR -> 200GR
    5OOML -> 500ML
    1OOGR -> 100GR
    25OML -> 250ML
    """

    def replace_match(match):
        value = match.group("value")
        unit = match.group("unit")

        fixed_value = value.replace("O", "0").replace("o", "0")
        fixed_unit = unit.upper()

        return f"{fixed_value}{fixed_unit}"

    return MEASUREMENT_FRAGMENT_PATTERN.sub(replace_match, text)

DEFAULT_RULES = {
    "preprocess": {
        "normalize_measurements": False,
        "ignore_keywords": [],
        "ignore_line_patterns": [],
        "replace_patterns": []
    },
    "item_cleanup": {
        "normalize_measurements": False,
        "ignore_item_names": [],
        "remove_name_prefix_patterns": [],
        "remove_name_suffix_patterns": [],
        "replace_patterns": []
    }
}


def load_profile_rules(profile=None) -> dict:
    if not profile or not profile.rules_json:
        return DEFAULT_RULES

    try:
        profile_rules = json.loads(profile.rules_json)
    except json.JSONDecodeError:
        return DEFAULT_RULES

    return merge_rules(DEFAULT_RULES, profile_rules)


def merge_rules(default_rules: dict, profile_rules: dict) -> dict:
    merged = json.loads(json.dumps(default_rules))

    for section_name, section_rules in profile_rules.items():
        if section_name not in merged:
            merged[section_name] = section_rules
            continue

        if isinstance(section_rules, dict):
            for key, value in section_rules.items():
                merged[section_name][key] = value
        else:
            merged[section_name] = section_rules

    return merged


def apply_replace_patterns(text: str, replace_patterns: list[dict]) -> str:
    result = text

    for rule in replace_patterns:
        pattern = rule.get("pattern")
        replacement = rule.get("replacement", "")

        if not pattern:
            continue

        result = re.sub(
            pattern,
            replacement,
            result,
            flags=re.IGNORECASE
        )

    return result


def should_ignore_line_by_rules(line: str, rules: dict) -> bool:
    preprocess_rules = rules.get("preprocess", {})

    ignore_keywords = preprocess_rules.get("ignore_keywords", [])
    ignore_line_patterns = preprocess_rules.get("ignore_line_patterns", [])

    normalized = line.lower()

    for keyword in ignore_keywords:
        if keyword.lower() in normalized:
            return True

    for pattern in ignore_line_patterns:
        if re.search(pattern, line, flags=re.IGNORECASE):
            return True

    return False


def apply_profile_rules_to_ocr_text(
    ocr_text: str,
    rules: dict
) -> str:
    preprocess_rules = rules.get("preprocess", {})

    replace_patterns = preprocess_rules.get("replace_patterns", [])

    cleaned_lines = []

    for raw_line in ocr_text.splitlines():
        line = raw_line.strip()
        
        if not line:
            continue

        if preprocess_rules.get("normalize_measurements", False):
            line = normalize_measurement_fragments(line)

        line = apply_replace_patterns(line, replace_patterns)

        if should_ignore_line_by_rules(line, rules):
            continue

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def clean_item_name_by_rules(
    name: str,
    rules: dict
) -> str:
    item_rules = rules.get("item_cleanup", {})

    remove_prefix_patterns = item_rules.get(
        "remove_name_prefix_patterns",
        []
    )
    remove_suffix_patterns = item_rules.get(
        "remove_name_suffix_patterns",
        []
    )
    replace_patterns = item_rules.get("replace_patterns", [])

    cleaned = name

    if item_rules.get("normalize_measurements", False):
        cleaned = normalize_measurement_fragments(cleaned)

    cleaned = apply_replace_patterns(cleaned, replace_patterns)

    for pattern in remove_prefix_patterns:
        cleaned = re.sub(
            pattern,
            "",
            cleaned,
            flags=re.IGNORECASE
        )

    for pattern in remove_suffix_patterns:
        cleaned = re.sub(
            pattern,
            "",
            cleaned,
            flags=re.IGNORECASE
        )

    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


def should_ignore_item_by_rules(
    name: str,
    rules: dict
) -> bool:
    item_rules = rules.get("item_cleanup", {})

    ignore_item_names = item_rules.get("ignore_item_names", [])

    normalized = name.strip().lower()

    for ignored_name in ignore_item_names:
        if normalized == ignored_name.lower():
            return True

    return False


def apply_profile_rules_to_items(
    items: list[dict],
    rules: dict
) -> list[dict]:
    cleaned_items = []

    for item in items:
        cleaned_name = clean_item_name_by_rules(
            item["name"],
            rules
        )

        if not cleaned_name:
            continue

        if should_ignore_item_by_rules(cleaned_name, rules):
            continue

        updated_item = {
            **item,
            "name": cleaned_name
        }

        cleaned_items.append(updated_item)

    return cleaned_items