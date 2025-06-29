import json
import zipfile
import os
import random
import time
import pygame
import sys
from datetime import datetime
import threading
import uuid
import glob
import platform
import pyttsx3
# ---------------- CONFIG ----------------

SCREEN_WIDTH = 480
SCREEN_HEIGHT = 800
IMAGE_AREA_HEIGHT = 480

CHINESE_FONT_SIZE = 32
MENU_FONT_SIZE = 36
SETTINGS_FONT_SIZE = 32

BACKGROUND_COLOR = (0, 0, 0)
TEXT_COLOR = (255, 255, 255)

SETTINGS_FILE = "settings.json"

# ---------------- LEARNING OBJECT ----------------

class LearningObjectV2:
    CURRENT_SCHEMA_VERSION = 2

    def __init__(self, english, pinyin, native, tags, delay_between_instruction_and_native=6, stats=None):
        self.schema_version = self.CURRENT_SCHEMA_VERSION
        self.english = english
        self.pinyin = pinyin
        self.native = native
        self.tags = tags  # full list of tags (string list)
        self.delay_between_instruction_and_native = delay_between_instruction_and_native
        self.stats = stats or {
            "times_played": 0,
            "times_correct": 0,
            "times_incorrect": 0,
            "last_played": None
        }

    def record_play(self):
        self.stats["times_played"] += 1
        self.stats["last_played"] = datetime.now().isoformat()

    def to_dict(self):
        return {
            "schema_version": self.schema_version,
            "english": self.english,
            "pinyin": self.pinyin,
            "native": self.native,
            "tags": self.tags,
            "delay_between_instruction_and_native": self.delay_between_instruction_and_native,
            "stats": self.stats
        }

    @staticmethod
    def from_dict(data):
        return LearningObjectV2(
            english=data.get("english", ""),
            pinyin=data.get("pinyin", ""),
            native=data.get("native", ""),
            tags=data.get("tags", []),
            delay_between_instruction_and_native=data.get("delay_between_instruction_and_native", 6),
            stats=data.get("stats", {
                "times_played": 0,
                "times_correct": 0,
                "times_incorrect": 0,
                "last_played": None
            })
        )
# ---------------- FILE HANDLING ----------------
def synthesize_instruction_tts(text, out_path):
    engine = pyttsx3.init()
    engine.setProperty('rate', 160)  # adjust speed to preference
    engine.save_to_file(text, out_path)
    engine.runAndWait()

def load_learning_object(zip_path):
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        metadata = json.loads(zipf.read('metadata.json'))
        lo = LearningObjectV2.from_dict(metadata)
        return lo

def update_learning_object_metadata(zip_path, lo):
    # Create a new zip file in memory with updated metadata
    temp_zip_path = zip_path + ".temp"
    with zipfile.ZipFile(zip_path, 'r') as old_zip:
        with zipfile.ZipFile(temp_zip_path, 'w') as new_zip:
            for item in old_zip.infolist():
                if item.filename != 'metadata.json':
                    new_zip.writestr(item, old_zip.read(item.filename))
            # Write the updated metadata.json
            metadata = json.dumps(lo.to_dict(), indent=2)
            new_zip.writestr('metadata.json', metadata)
    os.replace(temp_zip_path, zip_path)


def extract_audio_from_zip(zip_path, filename, extract_to):
    os.makedirs(extract_to, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        full_path = os.path.join(extract_to, unique_name)
        with open(full_path, 'wb') as f:
            f.write(zipf.read(filename))
        return full_path  # just the path is fine for deletion later
    
def safe_delete(path, retries=5, delay=0.05):
    for _ in range(retries):
        try:
            os.remove(path)
            return
        except PermissionError:
            time.sleep(delay)
    print(f"Failed to delete {path} after retries.")

def clean_temp_folder(exclude_files):
    """Delete all .mp3 files in the temp folder except those in exclude_files."""
    count = 0
    for f in glob.glob("temp/*.mp3"):
        count = count + 1
        print(str(count))
        if f not in exclude_files:
            try:
                os.remove(f)
            except Exception as e:
                print(f"Could not delete {f}: {e}")
    count = 0
    for f in glob.glob("temp/*.wav"):
        count = count + 1
        print(str(count))
        if f not in exclude_files:
            try:
                os.remove(f)
            except Exception as e:
                print(f"Could not delete {f}: {e}")

def safe_exit(app_instance=None):
    if app_instance and app_instance.playback_engine:
        app_instance.playback_engine.stop()
    pygame.quit()
    sys.exit(0)
# ---------------- PICKERS ----------------

def random_picker(learning_objects):
    return random.choice(learning_objects)

def weighted_picker(learning_objects):
    weights = []
    for lo in learning_objects:
        stats = lo.stats
        weight = (stats["times_incorrect"] + 1) / (stats["times_played"] + 1)
        weights.append(weight)
    total = sum(weights)
    normalized = [w / total for w in weights]
    return random.choices(learning_objects, weights=normalized, k=1)[0]

class SequentialPicker:
    def __init__(self, learning_objects):
        self.learning_objects = learning_objects
        self.index = 0

    def __call__(self, _):
        result = self.learning_objects[self.index]
        self.index = (self.index + 1) % len(self.learning_objects)
        return result

# ---------------- SETTINGS ----------------

class SettingsManager:
    def __init__(self):
        self.defaults = {
            "picker_mode": "Random",
            "instruction_delay": 6,
            "quiz_interval": 10,
            "show_native": True
        }
        self.load()

    def load(self):
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                self.data = json.load(f)
        else:
            self.data = self.defaults.copy()
            self.save()

    def save(self):
        with open(SETTINGS_FILE, "w") as f:
            json.dump(self.data, f, indent=2)

    def cycle_picker(self):
        modes = ["Random", "Weighted", "Sequential"]
        current_index = modes.index(self.data["picker_mode"])
        self.data["picker_mode"] = modes[(current_index + 1) % len(modes)]
        self.save()

    def adjust(self, key, delta, minimum=1, maximum=60):
        self.data[key] = max(minimum, min(maximum, self.data[key] + delta))
        self.save()
    
    def set(self, key, delta, value):
        self.data[key] = value
        self.save()

    def get(self, key, delta):
        return self.data[key]
    
# ---------------- ENGINE ----------------

class PlaybackEngine:
    def __init__(self, learning_objects, picker_function, settings, gui_callback):
        self.learning_objects = learning_objects
        self.picker_function = picker_function
        self.settings = settings
        self.gui_callback = gui_callback
        self.current_lo = None
        self.paused = False
        self.stopped = False
        self.skip_requested = False

    def play_loop(self):
        while not self.stopped:
            if not self.paused:
                self.current_lo = self.picker_function(self.learning_objects)
                self.current_lo.record_play()
                self.play_learning_object(self.current_lo)
                self.skip_requested = False
                update_learning_object_metadata(self.current_lo.file_path, self.current_lo)
            else:
                time.sleep(0.1)

    def wait_with_pause(self, duration):
        start = time.time()
        while time.time() - start < duration:
            if self.skip_requested or self.stopped:
                pygame.mixer.music.stop()
                return False
            while self.paused:
                pygame.mixer.music.pause()
                time.sleep(0.1)
            pygame.mixer.music.unpause()
            time.sleep(0.05)
        return True
    
    def wait_with_progress(self, total_duration, lo, mode):
        elapsed = 0
        step = 0.05  # GUI update interval

        while elapsed < total_duration:
            if self.skip_requested or self.stopped:
                pygame.mixer.music.stop()
                return False

            while self.paused:
                pygame.mixer.music.pause()
                time.sleep(0.1)

            pygame.mixer.music.unpause()

            time.sleep(step)
            elapsed += step

            progress = 1.0 - (elapsed / total_duration)
            self.gui_callback(lo, progress, mode)

        return True

    def play_learning_object(self, lo):
        # Try to extract instruction.mp3 (optional)
        try:
            instr_path = extract_audio_from_zip(lo.file_path, 'instruction.mp3', 'temp')
            use_tts = False
        except KeyError:
            # Fallback to TTS
            tts_id = uuid.uuid4().hex[:8]
            instr_path = os.path.join("temp", f"tts_instruction_{tts_id}.wav")

            synthesize_instruction_tts(lo.english, instr_path)
            use_tts = True

        # Native audio is still required
        native_path = extract_audio_from_zip(lo.file_path, 'native.mp3', 'temp')

        try:
            # INSTRUCTION
            self.state = "learning"
            pygame.mixer.music.load(instr_path)
            pygame.mixer.music.play()

            delay = self.settings.data["instruction_delay"]
            self.wait_with_progress(delay, lo, "learning")

            # NATIVE
            if self.skip_requested or self.stopped:
                return
            self.state = "reviewing"
            self.gui_callback(lo, 1.0, "reviewing")
            pygame.mixer.music.load(native_path)
            pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():
                if self.skip_requested or self.stopped:
                    pygame.mixer.music.stop()
                    return
                while self.paused:
                    pygame.mixer.music.pause()
                    time.sleep(0.1)
                pygame.mixer.music.unpause()
                time.sleep(0.1)

            # QUIZ INTERVAL
            self.wait_with_progress(self.settings.data["quiz_interval"], lo, "reviewing")
        finally:
            pygame.mixer.music.stop()
            try:
                pygame.mixer.music.load(os.devnull)  # forcibly unload the audio file
            except:
                pass
            time.sleep(0.05)

            # Clean temp folder, keeping only files we want
            keep_files = [native_path]
            if not use_tts:
                keep_files.append(instr_path)
            clean_temp_folder(keep_files)

            # Safely remove TTS file after it's released
            if use_tts and os.path.exists(instr_path):
                try:
                    os.remove(instr_path)
                except PermissionError:
                    time.sleep(0.1)
                    try:
                        os.remove(instr_path)
                    except Exception as e:
                        print(f"⚠️ Could not delete {instr_path}: {e}")



    def pause(self): self.paused = True
    def resume(self): self.paused = False
    def stop(self): self.stopped = True
    def skip(self): self.skip_requested = True

# ---------------- GUI ----------------

class LanguageAppliance:
    def __init__(self):
        pygame.init()
        pygame.mixer.init()
        if platform.system() == "Linux":
            pygame.mouse.set_visible(False)
        else:
            pygame.mouse.set_visible(True)
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.NOFRAME)
        pygame.display.set_caption("Language Machine")
        self.font_menu = pygame.font.Font("fonts/ComicNeue-Bold.ttf", MENU_FONT_SIZE)
        self.font_settings = pygame.font.Font("fonts/ComicNeue-Bold.ttf", SETTINGS_FONT_SIZE)
        self.font_chinese = pygame.font.Font("fonts/ZCOOLKuaiLe-Regular.ttf", CHINESE_FONT_SIZE)

        self.clock = pygame.time.Clock()
        self.smiley = pygame.image.load("smiley.png")
        self.smiley = pygame.transform.scale(self.smiley, (SCREEN_WIDTH, IMAGE_AREA_HEIGHT))
        self.menu_colors = [
            [(70, 130, 180), (50, 205, 50)],     # Row 0: blue, green
            [(255, 215, 0), (220, 20, 60)]       # Row 1: gold, red
        ]
        self.learning_controls_colors = [
            (70, 130, 180),  # Pause = steel blue
            (255, 215, 0),   # Skip = gold
            (220, 20, 60)    # Exit = crimson
        ]

        self.settings = SettingsManager()

        self.learning_objects = []
        os.makedirs("temp", exist_ok=True)
        for file in os.listdir("learning_objects"):
            if file.endswith(".xue"):
                path = os.path.join("learning_objects", file)
                lo = load_learning_object(path)
                lo.file_path = path
                self.learning_objects.append(lo)

        self.state = "main_menu"
        self.playback_engine = None
        self.play_thread = None

        self.menu_grid = [
            [("Start", self.start_learning_session), ("Settings", self.show_settings)],
            [("Stats", self.placeholder), ("Exit", safe_exit)]
        ]
    def wrap_text(self, text, font, max_width):
        words = text.split(" ")
        lines = []
        current_line = ""

        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            if font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return lines

    def run(self):
        running = True
        while running:
            self.clock.tick(30)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.quit()
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self.handle_touch(event.pos)
            self.draw()
        pygame.quit()

    def handle_touch(self, pos):
        x, y = pos
        if self.state == "main_menu" and y >= IMAGE_AREA_HEIGHT:
            col = x // (SCREEN_WIDTH // 2)
            row = (y - IMAGE_AREA_HEIGHT) // ((SCREEN_HEIGHT - IMAGE_AREA_HEIGHT) // 2)
            if row < 2 and col < 2:
                _, action = self.menu_grid[int(row)][int(col)]
                action()

        elif self.state == "settings" and y >= IMAGE_AREA_HEIGHT:
            button_height = (SCREEN_HEIGHT - IMAGE_AREA_HEIGHT) // 5
            button_row = (y - IMAGE_AREA_HEIGHT) // button_height
            if button_row == 0:
                self.settings.cycle_picker()
            elif button_row == 1:
                self.settings.adjust("instruction_delay", 1)
                if (self.settings.get("instruction_delay", 1) > 20):
                    self.settings.set("instruction_delay", 1, 1)
            elif button_row == 2:
                self.settings.adjust("quiz_interval", 1)
                if (self.settings.get("quiz_interval", 1) > 59):
                    self.settings.set("quiz_interval", 1, 1)
            elif button_row == 3:
                current = self.settings.data.get("show_native", True)
                self.settings.set("show_native", 1, not current)
            elif button_row == 4:
                self.state = "main_menu"

        elif self.state in ("learning", "reviewing") and y >= SCREEN_HEIGHT - 100:
            button_width = SCREEN_WIDTH // 3
            col = x // button_width
            if col == 0:
                if self.playback_engine.paused:
                    self.playback_engine.resume()
                else:
                    self.playback_engine.pause()
            elif col == 1:
                self.playback_engine.skip()
            elif col == 2:
                self.playback_engine.stop()
                clean_temp_folder("temp")
                if self.play_thread:
                    self.play_thread.join()
                self.state = "main_menu"

    def start_learning_session(self):
        self.state = "learning"
        picker = self.get_picker()
        self.playback_engine = PlaybackEngine(
            self.learning_objects, picker, self.settings, self.on_new_learning_object
        )
        self.play_thread = threading.Thread(target=self.playback_engine.play_loop)
        self.play_thread.start()

    def get_picker(self):
        mode = self.settings.data["picker_mode"]
        if mode == "Random": return random_picker
        elif mode == "Weighted": return weighted_picker
        elif mode == "Sequential": return SequentialPicker(self.learning_objects)
        else: return random_picker

    def on_new_learning_object(self, lo, progress=0, mode="learning"):
        self.current_lo = lo
        self.current_progress = progress
        self.state = mode

    def placeholder(self):
        print("Feature not implemented yet")

    def quit(self):
        if self.playback_engine:
            self.playback_engine.stop()
        if self.play_thread:
            self.play_thread.join()


    def show_settings(self):
        self.state = "settings"

    def draw(self):
        self.screen.fill(BACKGROUND_COLOR)
        self.screen.blit(self.smiley, (0, 0))

        if self.state == "main_menu":
            self.draw_menu()
        elif self.state == "learning":
            self.draw_learning_object()
            self.draw_learning_controls()
        elif self.state == "reviewing":
            self.draw_learning_object_review()
            self.draw_learning_controls()
        elif self.state == "settings":
            self.draw_settings()

        pygame.display.flip()

    def draw_menu(self):
        button_width = SCREEN_WIDTH // 2
        button_height = (SCREEN_HEIGHT - IMAGE_AREA_HEIGHT) // 2
        for row in range(2):
            for col in range(2):
                x = col * button_width
                y = IMAGE_AREA_HEIGHT + row * button_height
                color = self.menu_colors[row][col]
                pygame.draw.rect(self.screen, color, (x, y, button_width, button_height))
                label, _ = self.menu_grid[row][col]
                self.draw_centered_text(self.font_menu, label, x + button_width // 2, y + button_height // 2)


    def draw_learning_object(self):
        if hasattr(self, 'current_lo') and self.current_lo:
            english_lines = self.wrap_text(self.current_lo.english, self.font_menu, SCREEN_WIDTH - 40)

            line_height = 50
            total_height = len(english_lines) * line_height
            start_y = IMAGE_AREA_HEIGHT + (SCREEN_HEIGHT - IMAGE_AREA_HEIGHT - 100 - total_height) // 2

            for i, line in enumerate(english_lines):
                self.draw_centered_text(self.font_menu, line, SCREEN_WIDTH // 2, start_y + i * line_height)

            # Draw countdown bar
            bar_height = 10
            y_pos = IMAGE_AREA_HEIGHT - bar_height // 2
            bar_width = int(SCREEN_WIDTH * self.current_progress)
            pygame.draw.rect(self.screen, (200, 200, 200), (0, y_pos, bar_width, bar_height))


    def draw_learning_object_review(self):
        if hasattr(self, 'current_lo') and self.current_lo:
            # Get wrapped lines
            pinyin_lines = self.wrap_text(self.current_lo.pinyin, self.font_menu, SCREEN_WIDTH - 40)
            native_lines = self.wrap_text(self.current_lo.native, self.font_chinese, SCREEN_WIDTH - 40)

            # Respect settings
            show_native = self.settings.data.get("show_native", True)
            all_lines = pinyin_lines + (native_lines if show_native else [])

            # Draw lines centered vertically
            line_height = 50
            total_height = len(all_lines) * line_height
            start_y = IMAGE_AREA_HEIGHT + (SCREEN_HEIGHT - IMAGE_AREA_HEIGHT - 100 - total_height) // 2

            for i, line in enumerate(all_lines):
                font = self.font_menu if i < len(pinyin_lines) else self.font_chinese
                self.draw_centered_text(font, line, SCREEN_WIDTH // 2, start_y + i * line_height)
            # Draw countdown bar
            bar_height = 10
            y_pos = IMAGE_AREA_HEIGHT - bar_height // 2
            bar_width = int(SCREEN_WIDTH * self.current_progress)
            pygame.draw.rect(self.screen, (200, 200, 200), (0, y_pos, bar_width, bar_height))

    def draw_learning_controls(self):
        button_labels = [
            "Pause" if not self.playback_engine.paused else "Resume",
            "Skip",
            "Exit"
        ]

        button_width = SCREEN_WIDTH // 3
        button_height = 100
        y_pos = SCREEN_HEIGHT - button_height  # move to bottom of screen

        for i, label in enumerate(button_labels):
            x = i * button_width
            color = self.learning_controls_colors[i]

            pygame.draw.rect(self.screen, color, (x, y_pos, button_width, button_height))
            self.draw_centered_text(
                self.font_menu,
                label,
                x + button_width // 2,
                y_pos + button_height // 2
            )


    def draw_settings(self):
        options = [
            f"Picker: {self.settings.data['picker_mode']}",
            f"Instruction Delay: {self.settings.data['instruction_delay']}s",
            f"Quiz Interval: {self.settings.data['quiz_interval']}s",
            f"Show Characters: {'Yes' if self.settings.data.get('show_native', True) else 'No'}",
            "Back"
        ]
        button_height = (SCREEN_HEIGHT - IMAGE_AREA_HEIGHT) // 5
        for i, option in enumerate(options):
            y = IMAGE_AREA_HEIGHT + i * button_height
            pygame.draw.rect(self.screen, (0, 0, 0), (0, y, SCREEN_WIDTH, button_height))
            self.draw_centered_text(self.font_settings, option, SCREEN_WIDTH // 2, y + button_height // 2)

    def draw_centered_text(self, font, text, x, y, text_color=(255, 255, 255), outline_color=(0, 0, 0)):
        base_surface = font.render(text, True, text_color)
        outline_surface = font.render(text, True, outline_color)
        rect = base_surface.get_rect(center=(x, y))

        outline_thickness = 2  # Change this to 3 or more for thicker borders
        offsets = [
            (dx, dy)
            for dx in range(-outline_thickness, outline_thickness + 2)
            for dy in range(-outline_thickness, outline_thickness + 2)
            if not (dx == 0 and dy == 0)
        ]

        for dx, dy in offsets:
            offset_rect = rect.copy()
            offset_rect.move_ip(dx, dy)
            self.screen.blit(outline_surface, offset_rect)

        # Draw the main text on top
        self.screen.blit(base_surface, rect)


# MAIN ENTRY POINT
if __name__ == "__main__":
    app = LanguageAppliance()
    app.run()
