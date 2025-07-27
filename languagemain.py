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
    def __init__(self, english, pinyin, native, tags, delay_between_instruction_and_native=6, stats=None, flagged=False, language="chinese"):
        self.schema_version = self.CURRENT_SCHEMA_VERSION
        self.english = english
        self.pinyin = pinyin
        self.native = native
        self.tags = tags  # full list of tags (string list)
        self.delay_between_instruction_and_native = delay_between_instruction_and_native
        self.flagged = flagged
        self.language = language
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
            "stats": self.stats,
            "flagged": self.flagged
        }
    @staticmethod
    def from_dict(data):
        return LearningObjectV2(
            english=data.get("english", ""),
            pinyin=data.get("pinyin", ""),
            native=data.get("native", ""),
            tags=data.get("tags", []),
            flagged=data.get("flagged", False),
            stats=data.get("stats", {
                "times_played": 0,
                "times_correct": 0,
                "times_incorrect": 0,
                "last_played": None
            })
        )
# ---------------- FILE HANDLING ----------------

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
        #print(str(count))
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
    if app_instance and hasattr(app_instance, "on_raspberry_pi") and app_instance.on_raspberry_pi:
        try:
            app_instance.GPIO.cleanup()
        except Exception as e:
            print(f"GPIO cleanup failed: {e}")

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
            "show_native": True,
            "seconds_per_char": 1.0
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
    def __init__(self, learning_objects, picker_function, settings, gui_callback, mode="normal"):
        self.learning_objects = learning_objects
        self.picker_function = picker_function
        self.settings = settings
        self.gui_callback = gui_callback
        self.current_lo = None
        self.paused = False
        self.stopped = False
        self.skip_requested = False
        self.mode = mode
        
    def pause(self): self.paused = True
    def resume(self): self.paused = False
    def stop(self): self.stopped = True
    def skip(self): self.skip_requested = True

    def play_loop(self):
        while not self.stopped:
            if not self.paused:
                self.current_lo = self.picker_function(self.learning_objects)
                self.current_lo.record_play()

                print(f"Now playing: {self.current_lo.english}")  # Debug line
                #self.gui_callback(self.current_lo, 0.0, "learning","english")

                self.skip_requested = False
                self.play_learning_object(self.current_lo)

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
            self.gui_callback(lo, progress, mode, self.current_lang)

        return True

    def play_learning_object(self, lo):
        try:
            instr_path = extract_audio_from_zip(lo.file_path, 'instruction.mp3', 'temp')
            has_instr_audio = True
        except KeyError:
            instr_path = None
            has_instr_audio = False

        native_path = extract_audio_from_zip(lo.file_path, 'native.mp3', 'temp')

        # Decide dynamic order
        if self.mode == "chinese_first":
            first_audio = native_path
            second_audio = instr_path if has_instr_audio else None
            first_lang = "native"
            second_lang = "english"
            print("Made it to chinese block")
        else:
            first_audio = instr_path if has_instr_audio else None
            second_audio = native_path
            first_lang = "english"
            second_lang = "native"
            print("Made it to English block")

        try:
            # Phase 1 — Instruction
            self.state = "learning"
            self.current_progress = 0.0
            self.current_lang = first_lang  # <== NEW
            print(f"Now showing: {first_lang} -> {second_lang}")
            print(f"self.current_lang = {self.current_lang}, self.state = {self.state}")
            if first_audio:
                pygame.mixer.music.load(first_audio)
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

            if self.mode == "pinyin":
                delay = self.settings.data["instruction_delay"]
            else:
                seconds_per_char = self.settings.data.get("seconds_per_char", 1.0)
                delay = len(lo.native.strip()) * seconds_per_char
                delay = max(delay, 2)

            self.wait_with_progress(delay, lo, "learning")

            # Phase 2 — Review
            if self.skip_requested or self.stopped:
                return

            self.state = "reviewing"
            self.current_lang = second_lang  # <== NEW
            self.current_progress = 0.0
            print(f"Now showing: {first_lang} -> {second_lang}")
            print(f"self.current_lang = {self.current_lang}, self.state = {self.state}")

            if second_audio:
                pygame.mixer.music.load(second_audio)
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

            self.wait_with_progress(self.settings.data["quiz_interval"], lo, "reviewing")
            if hasattr(self.gui_callback, "__self__"):
                self.gui_callback.__self__.current_face = "smile_teeth"

        finally:
            pygame.mixer.music.stop()
            try:
                pygame.mixer.music.load(os.devnull)
            except:
                pass
            time.sleep(0.05)

            keep_files = [native_path]
            if instr_path:
                keep_files.append(instr_path)
            clean_temp_folder(keep_files)




# ---------------- GUI ----------------

class LanguageAppliance:
    def __init__(self):
        self.state = "main_menu"
        self.submenu_scroll = 0
        self.current_lang = "english"  # default
        self.dragged_during_touch = False
        self.on_raspberry_pi = platform.system() == "Linux"
        self.YES_BUTTON_PIN = 5
        self.NO_BUTTON_PIN = 16
        self.ROTARY_A_PIN = 20
        self.ROTARY_B_PIN = 21
        self.YES_LED_PIN = 12
        self.NO_LED_PIN = 26

        self.submenu_buttons = [
            [("English First", self.start_normal_mode)],
            [("Chinese First", self.start_chinese_first_mode)],
            [("Pinyin Practice", self.start_pinyin_mode)],
            [("Focused Learning", self.start_focused_learning_mode)],
            [("Listening Practice(Coming soon)", self.placeholder)],
            [("Grammar Trainer(Coming soon)", self.placeholder)],
            [("Reading Practice(Coming soon)", self.placeholder)],
            [("Story Mode(Coming soon)", self.placeholder)],
            [("Back to Main Menu", self.go_back_to_main)],
        ]
        self.face_images = {
            "default": pygame.transform.scale(pygame.image.load("smiley.png"), (SCREEN_WIDTH, IMAGE_AREA_HEIGHT)),
            "smile_teeth": pygame.transform.scale(pygame.image.load("smile_teeth.png"), (SCREEN_WIDTH, IMAGE_AREA_HEIGHT)),
            "neutral": pygame.transform.scale(pygame.image.load("neutral.png"), (SCREEN_WIDTH, IMAGE_AREA_HEIGHT)),
            "concerned": pygame.transform.scale(pygame.image.load("concerned.png"), (SCREEN_WIDTH, IMAGE_AREA_HEIGHT)),
            "frown": pygame.transform.scale(pygame.image.load("frown.png"), (SCREEN_WIDTH, IMAGE_AREA_HEIGHT)),
            "frown_eyes_closed": pygame.transform.scale(pygame.image.load("frown_closed.png"), (SCREEN_WIDTH, IMAGE_AREA_HEIGHT)),
            "frown_tear": pygame.transform.scale(pygame.image.load("frown_tear.png"), (SCREEN_WIDTH, IMAGE_AREA_HEIGHT)),
            "look_left": pygame.transform.scale(pygame.image.load("look_left.png"), (SCREEN_WIDTH, IMAGE_AREA_HEIGHT)),
            "look_right": pygame.transform.scale(pygame.image.load("look_right.png"), (SCREEN_WIDTH, IMAGE_AREA_HEIGHT)),
            "disturbed": pygame.transform.scale(pygame.image.load("disturbed.png"), (SCREEN_WIDTH, IMAGE_AREA_HEIGHT))
        }
        if self.on_raspberry_pi:
            import lgpio
            try:
                self.gpio_chip = lgpio.gpiochip_open(0)

                # Button pins (input with pull-up logic handled in software)
                self.YES_BUTTON_PIN = 5
                self.NO_BUTTON_PIN = 16

                # Rotary encoder pins
                self.ROTARY_A_PIN = 20
                self.ROTARY_B_PIN = 21

                # LED pins (output)
                self.YES_LED_PIN = 12
                self.NO_LED_PIN = 26

                # Configure pins
                for pin in [self.YES_BUTTON_PIN, self.NO_BUTTON_PIN, self.ROTARY_A_PIN, self.ROTARY_B_PIN]:
                    lgpio.gpio_claim_input(self.gpio_chip, pin)

                for pin in [self.YES_LED_PIN, self.NO_LED_PIN]:
                    lgpio.gpio_claim_output(self.gpio_chip, pin)
                    lgpio.gpio_write(self.gpio_chip, pin, 1)  # LEDs off

                # Track last rotary state
                self.last_rotary_state = lgpio.gpio_read(self.gpio_chip, self.ROTARY_A_PIN)
            except Exception as e:
                print(f"GPIO setup failed: {e}")
                self.on_raspberry_pi = False
        else:
            print("Running in virtual mode (no GPIO)")
            self.last_rotary_state = 1  # dummy value     
        self.current_face = "default"
        self.face_timer = 0
        self.last_face_change = time.time()

        self.show_english_line = False
        self.dragging = False
        self.last_drag_y = 0
        self.scroll_velocity = 0
        self.last_scroll_time = time.time()
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
            (70, 130, 180),  # Pause
            (255, 215, 0),   # Skip
            (220, 20, 60),   # Exit
            (138, 43, 226)   # Flag = BlueViolet
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
    def go_back_to_main(self):
        self.state = "main_menu"
    def flag_current_object(self):
        if hasattr(self, 'current_lo') and self.current_lo:
            self.current_lo.flagged = not self.current_lo.flagged
            update_learning_object_metadata(self.current_lo.file_path, self.current_lo)
            print(f"{'Flagged' if self.current_lo.flagged else 'Unflagged'}: {self.current_lo.english}")

    def start_normal_mode(self):
        self.learning_objects = []
        for file in os.listdir("learning_objects"):
            if file.endswith(".xue"):
                path = os.path.join("learning_objects", file)
                lo = load_learning_object(path)
                lo.file_path = path
                self.learning_objects.append(lo)
        self.launch_learning()
    def start_chinese_first_mode(self):
        self.learning_objects = []
        for file in os.listdir("learning_objects"):
            if file.endswith(".xue"):
                path = os.path.join("learning_objects", file)
                lo = load_learning_object(path)
                lo.file_path = path
                self.learning_objects.append(lo)
        self.launch_learning(mode="chinese_first")

    def start_pinyin_mode(self):
        self.learning_objects = []
        for file in os.listdir("pinyin_practice"):
            if file.endswith(".xue"):
                path = os.path.join("pinyin_practice", file)
                lo = load_learning_object(path)
                lo.file_path = path
                self.learning_objects.append(lo)
        self.launch_learning()
    def start_focused_learning_mode(self):
        self.learning_objects = []
        for file in os.listdir("learning_objects"):
            if file.endswith(".xue"):
                path = os.path.join("learning_objects", file)
                lo = load_learning_object(path)
                lo.file_path = path
                if lo.flagged:
                    self.learning_objects.append(lo)

        if not self.learning_objects:
            print("No flagged learning objects found.")
            return

        self.launch_learning(mode="focused")

    def launch_learning(self, mode="normal"):
        if self.play_thread and self.play_thread.is_alive():
            print("Warning: learning session already running. Skipping new launch.")
            return

        self.playback_engine = PlaybackEngine(
            self.learning_objects,
            self.get_picker(),
            self.settings,
            self.on_new_learning_object,
            mode=mode
        )

        self.play_thread = threading.Thread(target=self.playback_engine.play_loop)
        self.play_thread.start()
        self.state = "learning"


    def run(self):
        running = True
        while running:
            self.clock.tick(30)
            scroll_limit = max(0, len(self.submenu_buttons) * 100 - (SCREEN_HEIGHT - IMAGE_AREA_HEIGHT))
            scrolling_enabled = scroll_limit > 0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.quit()
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self.dragging = True
                    self.last_drag_y = event.pos[1]
                    self.dragged_during_touch = False  # Reset on touch start

                elif event.type == pygame.MOUSEMOTION and self.dragging and scrolling_enabled:
                    now = time.time()
                    dy = self.last_drag_y - event.pos[1]
                    self.last_drag_y = event.pos[1]
                    self.submenu_scroll += dy
                    self.dragged_during_touch = True  # Register that a drag occurred

                    # Clamp the scroll area
                    max_scroll = max(0, len(self.submenu_buttons) * 100 - (SCREEN_HEIGHT - IMAGE_AREA_HEIGHT))
                    #self.submenu_scroll = max(0, min(self.submenu_scroll, max_scroll))

                    # Calculate velocity for inertia
                    dt = now - self.last_scroll_time
                    if dt > 0:
                        self.scroll_velocity = dy / dt
                        self.last_scroll_time = now
                    #if abs(self.scroll_velocity) < 5:
                    #    self.scroll_velocity = 0
                elif event.type == pygame.MOUSEBUTTONUP:
                    if not self.dragged_during_touch:
                        # This was a tap, not a scroll — handle it!
                        if self.state == "submenu":
                            self.handle_submenu_touch(*event.pos)
                        else:
                            self.handle_touch(event.pos)
                    self.dragging = False
                    self.scroll_velocity = 0



                        

            if not self.dragging and abs(self.scroll_velocity) > 0.1:
                now = time.time()
                dt = now - self.last_scroll_time
                self.last_scroll_time = now

                # Apply velocity
                self.submenu_scroll += self.scroll_velocity * dt

                # Clamp the scroll area
                max_scroll = max(0, len(self.submenu_buttons) * 100 - (SCREEN_HEIGHT - IMAGE_AREA_HEIGHT))
                self.submenu_scroll = max(0, min(self.submenu_scroll, max_scroll))

                # Apply deceleration
                self.scroll_velocity *= 0.75  # smaller = faster deceleration
            # BOUNCE-BACK CORRECTION
            max_scroll = max(0, len(self.submenu_buttons) * 100 - (SCREEN_HEIGHT - IMAGE_AREA_HEIGHT))
            bounce_force = 0.2  # how hard it snaps back
            damping = 0.7       # how much it slows the bounce

            # If too far up
            if self.submenu_scroll < 0:
                self.scroll_velocity += (-self.submenu_scroll) * bounce_force
                self.scroll_velocity *= damping

            # If too far down
            elif self.submenu_scroll > max_scroll:
                self.scroll_velocity += (max_scroll - self.submenu_scroll) * bounce_force
                self.scroll_velocity *= damping

            # Check buttons
            if self.on_raspberry_pi:
                import lgpio
                # Yes button
                if lgpio.gpio_read(self.gpio_chip, self.YES_BUTTON_PIN) == 0:
                    print("Yes button pressed")
                    lgpio.gpio_write(self.gpio_chip, self.YES_LED_PIN, 1)
                else:
                    lgpio.gpio_write(self.gpio_chip, self.YES_LED_PIN, 0)

                # No button
                if lgpio.gpio_read(self.gpio_chip, self.NO_BUTTON_PIN) == 0:
                    print("No button pressed")
                    lgpio.gpio_write(self.gpio_chip, self.NO_LED_PIN, 1)
                else:
                    lgpio.gpio_write(self.gpio_chip, self.NO_LED_PIN, 0)

                # Rotary encoder
                rotary_a = lgpio.gpio_read(self.gpio_chip, self.ROTARY_A_PIN)
                rotary_b = lgpio.gpio_read(self.gpio_chip, self.ROTARY_B_PIN)
                if rotary_a != self.last_rotary_state:
                    if rotary_b != rotary_a:
                        print("Rotated right")
                    else:
                        print("Rotated left")
                    self.last_rotary_state = rotary_a

            self.draw()
        pygame.quit()
    def handle_submenu_touch(self, x, y):
        scroll_y = y + self.submenu_scroll - IMAGE_AREA_HEIGHT
        button_height = 100
        for i, row in enumerate(self.submenu_buttons):
            row_y = i * button_height
            if row_y <= scroll_y <= row_y + button_height:
                label, action = row[0]
                action()
                break


    def handle_touch(self, pos):
        x, y = pos
        # Virtual button zones (top left and top right corners)
        if not self.on_raspberry_pi and y < 100:
            if x < 100:
                print("Virtual NO button pressed")
            elif x > SCREEN_WIDTH - 100:
                print("Virtual YES button pressed")
        if self.state == "main_menu" and y >= IMAGE_AREA_HEIGHT:
            col = x // (SCREEN_WIDTH // 2)
            row = (y - IMAGE_AREA_HEIGHT) // ((SCREEN_HEIGHT - IMAGE_AREA_HEIGHT) // 2)
            if row < 2 and col < 2:
                _, action = self.menu_grid[int(row)][int(col)]
                action()
        elif self.state == "submenu":
            self.dragging = True
            self.last_drag_y = y

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
            button_width = SCREEN_WIDTH // 4
            col = x // button_width
            if col == 0:
                if self.playback_engine.paused:
                    self.playback_engine.resume()
                else:
                    self.playback_engine.pause()
            elif col == 1:
                self.playback_engine.skip()
            elif col == 2:
                self.playback_engine.resume()
                self.playback_engine.stop()
                clean_temp_folder("temp")
                if self.play_thread:
                    self.play_thread.join()
                self.state = "main_menu"
            elif col == 3:
                self.flag_current_object()


    def start_learning_session(self):
        self.state = "submenu"
        self.submenu_scroll = 0


    def get_picker(self):
        mode = self.settings.data["picker_mode"]
        if mode == "Random": return random_picker
        elif mode == "Weighted": return weighted_picker
        elif mode == "Sequential": return SequentialPicker(self.learning_objects)
        else: return random_picker

    def on_new_learning_object(self, lo, progress=0, mode="learning", lang="english"):
        self.current_lo = lo
        self.current_progress = progress
        self.state = mode
        self.current_lang = lang
        self.show_english_line = False



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
        self.screen.blit(self.face_images[self.current_face], (0, 0))
        if self.state == "main_menu":
            self.draw_menu()
        elif self.state == "submenu":
            self.draw_submenu()
        elif self.state in ("learning", "reviewing"):
            self.draw_learning_object()
            self.draw_learning_controls()
        elif self.state == "settings":
            self.draw_settings()
        # Idle face animation (random look left/right)
        if self.state not in ("learning", "reviewing"):
            now = time.time()
            if now - self.last_face_change > 0.2:  # Check every 3 seconds
                if random.random() < 0.1:  # 30% chance to change
                    self.current_face = random.choice(["default", "look_left", "look_right", "neutral"])
                else:
                    pass
                    #self.current_face = "default"
                self.last_face_change = now
        elif(self.state == "learning"):
            # When in learning or reviewing, keep default face
            
            self.current_face = "default"
        if not self.on_raspberry_pi:
            pygame.draw.rect(self.screen, (255, 0, 0), (0, 0, 100, 100))  # Virtual NO
            pygame.draw.rect(self.screen, (0, 255, 0), (SCREEN_WIDTH - 100, 0, 100, 100))  # Virtual YES

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

    def draw_submenu(self):
        y_offset = IMAGE_AREA_HEIGHT - self.submenu_scroll
        button_height = 100

        colors = [(70, 130, 180), (50, 205, 50)]  # Blue, Green

        for i, row in enumerate(self.submenu_buttons):
            label, _ = row[0]
            color = colors[i % 2]
            pygame.draw.rect(self.screen, color, (0, y_offset, SCREEN_WIDTH, button_height))
            self.draw_centered_text(self.font_menu, label, SCREEN_WIDTH // 2, y_offset + button_height // 2)
            y_offset += button_height

    def draw_learning_object(self):
        if not hasattr(self, 'current_lo') or not self.current_lo:
            return

        lo = self.current_lo
        #print(getattr(self, 'current_lang'))
        current_lang = getattr(self, 'current_lang', 'english')
        lines = []
        #print(current_lang)
        if current_lang == "native":
            if lo.language == "french":
                # Treat "pinyin" as the full French sentence
                french_lines = self.wrap_text(lo.pinyin, self.font_menu, SCREEN_WIDTH - 40)
                lines.extend((line, self.font_menu) for line in french_lines)
            else:
                # Mandarin case
                pinyin_lines = self.wrap_text(lo.pinyin, self.font_menu, SCREEN_WIDTH - 40)
                lines.extend((line, self.font_menu) for line in pinyin_lines)

                if self.settings.data.get("show_native", True):
                    native_lines = self.wrap_text(lo.native, self.font_chinese, SCREEN_WIDTH - 40)
                    lines.extend((line, self.font_chinese) for line in native_lines)


        elif current_lang == "english":
            english_lines = self.wrap_text(lo.english, self.font_menu, SCREEN_WIDTH - 40)
            lines.extend((line, self.font_menu) for line in english_lines)

        # Draw text lines
        line_height = 50
        total_height = len(lines) * line_height
        start_y = IMAGE_AREA_HEIGHT + (SCREEN_HEIGHT - IMAGE_AREA_HEIGHT - 100 - total_height) // 2

        for i, (line, font) in enumerate(lines):
            self.draw_centered_text(font, line, SCREEN_WIDTH // 2, start_y + i * line_height)

        # Countdown bar
        bar_height = 10
        y_pos = IMAGE_AREA_HEIGHT - bar_height // 2
        bar_width = int(SCREEN_WIDTH * self.current_progress)
        pygame.draw.rect(self.screen, (0, 200, 0), (0, y_pos, bar_width, bar_height))

    def draw_learning_controls(self):
        button_labels = [
            "Pause" if not self.playback_engine.paused else "Resume",
            "Skip",
            "Exit",
            "Flag"
        ]

        button_width = SCREEN_WIDTH // 4
        button_height = 100
        y_pos = SCREEN_HEIGHT - button_height  # move to bottom of screen

        for i, label in enumerate(button_labels):
            x = i * button_width

            if i == 3:  # Flag button
                if hasattr(self, 'current_lo') and self.current_lo and self.current_lo.flagged:
                    color = (186, 85, 211)  # Light purple when flagged
                else:
                    color = (138, 43, 226)  # Dark purple when not flagged
            else:
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
