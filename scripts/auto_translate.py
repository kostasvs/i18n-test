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
        ["git", "diff", "HEAD^", "HEAD", f"{LOCALES_DIR}/{SOURCE_LANG}.json"]
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
    # read prompt text from file
    with open("scripts/translate_prompt.txt", encoding="utf-8") as f:
        prompt = f.read()

    # replace placeholders in prompt
    prompt = prompt.replace("%json_text%", json_text)
    prompt = prompt.replace("%target_lang%", target_lang)

    resp = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "system", "content": prompt}],
        response_format={
            "type": "json",
        },
        temperature=0
    )
    return resp.choices[0].message.content.strip()


def translate_text_partitioned(json_data, target_lang, chars_per_partition):
    """Translate JSON data in partitions to avoid token limits."""
    partitions = []
    current_partition = {}
    char_count = 0

    for key, value in json_data.items():
        current_partition[key] = value
        char_count += len(key) + len(value)
        if char_count >= chars_per_partition:
            partitions.append(current_partition)
            current_partition = {}
            char_count = 0

    if current_partition:
        partitions.append(current_partition)

    translated_data = {}
    remaining_keys = len(json_data)
    for part in partitions:
        print(f"Translating {len(part)} keys (total remaining: {remaining_keys}) for {target_lang}...")
        remaining_keys -= len(part)
        translated_part = translate_partition(part, target_lang)
        if not translated_part:
            print("Retrying...")
            translated_part = translate_partition(part, target_lang)
            if not translated_part:
                raise ValueError("Translation failed after 2 tries.")
        translated_data.update(translated_part)

    return translated_data


def translate_partition(part, target_lang):
    json_text = json.dumps(part, ensure_ascii=False, indent=2)
    translated_text = translate_text(json_text, target_lang)
    try:
        return json.loads(translated_text)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON for {target_lang}: {e}")
        print(f"JSON: {translated_text}\n")
        return {}

def main():
    # ensure target language is set
    if not TARGET_LANG:
        print("TARGET_LANG environment variable is not set. Exiting.")
        return

    # ensure target language is not the source language
    if TARGET_LANG == SOURCE_LANG:
        print(f"Target language {TARGET_LANG} is the same as source language {SOURCE_LANG}. No translation needed.")
        return

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
    translated_data = translate_text_partitioned(json_to_translate, lang_name, chars_per_partition=5000)

    # Update target_data with translated values
    for key, value in translated_data.items():
        target_data[key] = value

    # Save updated file
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(target_data, f, ensure_ascii=False, indent=4)

    print(f"Translations updated for {lang_name}.")


if __name__ == "__main__":
    main()
