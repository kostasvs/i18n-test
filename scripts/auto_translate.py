import json
import os
import subprocess
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

LOCALES_DIR = "locales"
SOURCE_LANG = "en"

# Define language names
# Note: This list used to get the language name from the locale code.
# Languages listed here are not necessarily translated.
# The actual list of languages is in auto_translate.yml which passes them as environment variable TARGET_LANG.
LANG_NAMES = {
    "el": "Greek",
    "ar": "Arabic",
    "cs": "Czech",
    "da": "Danish",
    "de": "German",
    "es": "Spanish",
    "fi": "Finnish",
    "fr": "French",
    "hu": "Hungarian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "lt": "Lithuanian",
    "nl": "Dutch",
    "pl": "Polish",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "zh-cn": "Chinese (Simplified)",
    "zh-tw": "Chinese (Traditional)",
}
TARGET_LANG = os.environ["TARGET_LANG"]


def get_source_dict():
    """Returns a dict of {key: value} for all keys in source json."""
    with open(f"{LOCALES_DIR}/{SOURCE_LANG}.json", encoding="utf-8") as f:
        current = json.load(f)

    return current


def get_changed_keys():
    """Returns a list for changed or new keys in source json."""
    # If the event is a manual trigger, don't check for changes, only missing translations will be added
    event_name = os.getenv("GITHUB_EVENT_NAME")
    if event_name == "workflow_dispatch":
        return []

    # Compare last commit of source json to current
    diff_output = subprocess.check_output(
        ["git", "diff", "HEAD~1", "HEAD", f"{LOCALES_DIR}/{SOURCE_LANG}.json"]
    ).decode()

    # parse diff_output to detect exact changes
    changes = []
    for line in diff_output.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            # This is a new or changed line
            key_value = line[1:].strip()
            if ":" in key_value:
                key = key_value.split(":", 1)[0].strip().strip('"')
                changes.append(key)

    return changes


def translate_text(json_text, target_lang):
    """Translate keeping placeholders intact."""
    prompt = f"""
    You are a translation engine for a role-playing business simulation video game. 
    Translate only the JSON values in the following JSON to {target_lang}. 
    Keep:
    - All keys exactly the same
    - All placeholders inside curly braces unchanged
    - All HTML tags (e.g. <u> and </u>) unchanged
    - The JSON structure unchanged
    Text in other delimiters, e.g. **bold** or 'text', should be translated normally.

    Pay attention to possessive nouns containing placeholders/tags, e.g.:
    - "{{businessname}}'s {{itemname}}" should treated as "the {{itemname}} of {{businessname}}" when translating
    - "<u>{{businessname}}</u>'s {{itemname}}" should be treated similarly, keeping the <u> tags intact.

    Any "producers" in placeholders refer to item producers or item containers, e.g. boxes, shelves, machines, etc.

    Do not add extra text, explanations, or comments. 
    Output valid JSON only.

    JSON to translate:
    {json_text}
    """
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": prompt}],
        temperature=0
    )
    return resp.choices[0].message.content.strip()


def translate_text_partitioned(json_data, target_lang, max_keys_per_partition):
    """Translate JSON data in partitions to avoid token limits."""
    partitions = []
    current_partition = {}

    for key, value in json_data.items():
        current_partition[key] = value
        if len(current_partition) >= max_keys_per_partition:
            partitions.append(current_partition)
            current_partition = {}

    if current_partition:
        partitions.append(current_partition)

    translated_data = {}
    for part in partitions:
        json_text = json.dumps(part, ensure_ascii=False, indent=2)
        print(f"Translating {len(part)} keys for {target_lang}...")
        translated_text = translate_text(json_text, target_lang)
        translated_part = json.loads(translated_text)
        translated_data.update(translated_part)

    return translated_data


def main():
    all_keys = get_source_dict()
    changes = get_changed_keys()
    target_path = f"{LOCALES_DIR}/{TARGET_LANG}.json"
    lang_name = LANG_NAMES.get(TARGET_LANG, TARGET_LANG)

    # Load existing translations
    if os.path.exists(target_path):
        with open(target_path, encoding="utf-8") as f:
            target_data = json.load(f)
            # Remove keys not in source json
            target_data = {k: v for k, v in target_data.items() if k in all_keys}
            # Make json of all added or changed keys
            json_to_translate = {k: all_keys[k] for k in all_keys if k not in target_data or k in changes}
    else:
        # If the target file does not exist, create a new one with all keys
        target_data = {}
        json_to_translate = all_keys

    if not json_to_translate:
        print(f"No changes to translate for {lang_name}.")
        return

    # Translate the JSON text
    translated_data = translate_text_partitioned(json_to_translate, lang_name, max_keys_per_partition=100)

    # Update target_data with translated values
    for key, value in translated_data.items():
        target_data[key] = value

    # Save updated file
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(target_data, f, ensure_ascii=False, indent=4)

    print(f"Translations updated for {lang_name}.")


if __name__ == "__main__":
    main()
