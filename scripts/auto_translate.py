import json
import os
import subprocess
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

LOCALES_DIR = "locales"
SOURCE_LANG = "en"
TARGET_LANGS = {"da": "Danish", "el": "Greek"}


def get_source_dict():
    """Returns a dict of {key: value} for all keys in source json."""
    with open(f"{LOCALES_DIR}/{SOURCE_LANG}.json", encoding="utf-8") as f:
        current = json.load(f)

    return current


def get_changed_keys():
    """Returns a list for changed or new keys in source json."""
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
    You are a translation engine. 
    Translate only the JSON values in the following JSON to {target_lang}. 
    Keep:
    - All keys exactly the same
    - All placeholders in curly braces unchanged
    - All HTML tags (e.g., <u>…</u>) unchanged
    - The JSON structure unchanged

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


def main():
    all_keys = get_source_dict()
    changes = get_changed_keys()
    if not changes:
        print(f"No new or changed lines detected in {LOCALES_DIR}/{SOURCE_LANG}.json.")
        return

    for lang, lang_name in TARGET_LANGS:
        target_path = f"{LOCALES_DIR}/{lang}.json"

        # Load existing translations
        if os.path.exists(target_path):
            with open(target_path, encoding="utf-8") as f:
                target_data = json.load(f)
        else:
            target_data = {}

        # Remove keys not in source json
        target_data = {k: v for k, v in target_data.items() if k in all_keys}

        # Make json of all added or changed keys
        json_to_translate = {
            k: all_keys[k] for k in changes if k in all_keys
        }
        if not json_to_translate:
            print(f"No changes to translate for {lang_name}.")
            continue

        # Translate the JSON text
        json_text = json.dumps(json_to_translate, ensure_ascii=False, indent=4)
        translated_text = translate_text(json_text, lang_name)

        # Parse the translated text back to JSON
        try:
            translated_data = json.loads(translated_text)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON for {lang_name}: {e}")
            continue

        # Update target_data with translated values
        for key, value in translated_data.items():
            target_data[key] = value

        # Save updated file
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(target_data, f, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    main()
