import os
import json
import zipfile
import sqlite3
import shutil
import re

# CONFIGURE PATHS
DECK_FOLDER = "tones_extracted"        # folder where you extracted the .apkg
OUTPUT_FOLDER = "xue_output_tones"     # where .xue files will be saved
MEDIA_FOLDER = os.path.join(OUTPUT_FOLDER, "media")
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(MEDIA_FOLDER, exist_ok=True)

# TONE MAP
tone_map = {
    'a': ['ā', 'á', 'ǎ', 'à'],
    'e': ['ē', 'é', 'ě', 'è'],
    'i': ['ī', 'í', 'ǐ', 'ì'],
    'o': ['ō', 'ó', 'ǒ', 'ò'],
    'u': ['ū', 'ú', 'ǔ', 'ù'],
    'ü': ['ǖ', 'ǘ', 'ǚ', 'ǜ']
}

def numbered_to_tone(pinyin_num):
    if not pinyin_num or not pinyin_num[-1].isdigit():
        return pinyin_num
    tone = int(pinyin_num[-1])
    base = pinyin_num[:-1]
    for vowel in "aeiouü":
        if vowel in base:
            return base.replace(vowel, tone_map[vowel][tone - 1])
    return pinyin_num

def make_safe_filename(text):
    text = re.sub(r'<[^>]+>', '', text)     # remove HTML tags
    text = text.replace("ü", "v")           # convert ü to v
    return re.sub(r'[\\/*?:"<>|]', "", text) # remove invalid filename chars

# Load media map
with open(os.path.join(DECK_FOLDER, "media"), "r", encoding="utf-8") as f:
    media_map = json.load(f)

# Connect to collection DB
conn = sqlite3.connect(os.path.join(DECK_FOLDER, "collection.anki2"))
cursor = conn.cursor()
cursor.execute("SELECT flds FROM notes")
rows = cursor.fetchall()
conn.close()

print(f"Found {len(rows)} notes. Starting conversion...\n")

count = 0
for row in rows:
    fields = row[0].split("\x1f")
    if len(fields) < 2:
        continue

    audio_tag = fields[0]
    pinyin_raw = fields[1].strip()

    if not pinyin_raw or "]" not in audio_tag:
        continue

    try:
        filename = audio_tag.split("sound:")[1].split("]")[0]
    except:
        continue

    if filename not in media_map.values():
        continue

    # Tone conversion and safe filename
    pinyin_tone = numbered_to_tone(pinyin_raw)
    safe_filename = make_safe_filename(pinyin_raw)

    # Get MP3 source path
    source_key = next((k for k, v in media_map.items() if v == filename), None)
    if not source_key:
        continue
    source_mp3 = os.path.join(DECK_FOLDER, source_key)
    dest_mp3 = os.path.join(MEDIA_FOLDER, f"{safe_filename}_native.mp3")

    # Avoid overwriting files
    if os.path.exists(dest_mp3):
        print(f"⚠️ Skipping duplicate: {safe_filename}")
        continue

    try:
        shutil.copy(source_mp3, dest_mp3)
    except Exception as e:
        print(f"❌ Could not copy {source_mp3}: {e}")
        continue

    # Create xue object
    xue_obj = {
        "schema_version": 2,
        "english": pinyin_tone,
        "pinyin": pinyin_tone,
        "native": pinyin_tone,
        "tags": ["tone_practice"],
        "delay_between_instruction_and_native": 2,
        "stats": {
            "times_played": 0,
            "times_correct": 0,
            "times_incorrect": 0,
            "last_played": None
        }
    }

    # Save as .xue
    zip_path = os.path.join(OUTPUT_FOLDER, f"{safe_filename}.xue")
    try:
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            zipf.writestr("metadata.json", json.dumps(xue_obj, ensure_ascii=False, indent=2))
            zipf.write(dest_mp3, arcname="native.mp3")
        count += 1
        if count % 100 == 0:
            print(f"Processed {count} cards...")
    except Exception as e:
        print(f"❌ Could not write {zip_path}: {e}")

print(f"\n✅ Finished! {count} .xue files written to: {OUTPUT_FOLDER}")
