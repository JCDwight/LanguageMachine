import tkinter as tk
from tkinter import filedialog, messagebox
import zipfile
import json
import os
import pygame
from datetime import datetime

TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)
pygame.mixer.init()

class LearningObjectV2:
    CURRENT_SCHEMA_VERSION = 2

    def __init__(self, english, pinyin, native, tags, delay_between_instruction_and_native=6, stats=None):
        self.schema_version = self.CURRENT_SCHEMA_VERSION
        self.english = english
        self.pinyin = pinyin
        self.native = native
        self.tags = tags
        self.delay_between_instruction_and_native = delay_between_instruction_and_native
        self.stats = stats or {
            "times_played": 0,
            "times_correct": 0,
            "times_incorrect": 0,
            "last_played": None
        }

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

class EditorApp:
    def __init__(self, master):
        self.master = master
        master.title("LearningObject V2 Editor")

        self.fields = {}
        self.instruction_path = ""
        self.native_path = ""
        self.image_path = ""

        field_names = [
            ("English", "english"),
            ("Pinyin", "pinyin"),
            ("Native", "native"),
            ("Tags (comma separated)", "tags"),
            ("Delay (sec)", "delay")
        ]

        for idx, (label_text, key) in enumerate(field_names):
            label = tk.Label(master, text=label_text)
            label.grid(row=idx, column=0, sticky="e")
            entry = tk.Entry(master, width=50)
            entry.grid(row=idx, column=1, padx=5, pady=2)
            self.fields[key] = entry

        tk.Button(master, text="Open Existing .xue", command=self.open_existing).grid(row=6, column=0, columnspan=2, pady=5)
        tk.Button(master, text="Select Instruction Audio", command=self.select_instruction).grid(row=7, column=0, columnspan=2, pady=5)
        tk.Button(master, text="Select Native Audio", command=self.select_native).grid(row=8, column=0, columnspan=2, pady=5)
        tk.Button(master, text="Select Optional Image", command=self.select_image).grid(row=9, column=0, columnspan=2, pady=5)
        tk.Button(master, text="▶ Play Instruction", command=self.play_instruction).grid(row=10, column=0, pady=5)
        tk.Button(master, text="▶ Play Native", command=self.play_native).grid(row=10, column=1, pady=5)
        tk.Button(master, text="Save LearningObject", command=self.save_learning_object).grid(row=11, column=0, columnspan=2, pady=10)

    def open_existing(self):
        path = filedialog.askopenfilename(title="Open .xue File", filetypes=[("LearningObject Files", "*.xue")])
        if not path:
            return

        try:
            with zipfile.ZipFile(path, 'r') as zipf:
                metadata = json.loads(zipf.read('metadata.json'))
                lo = LearningObjectV2.from_dict(metadata)

                #self.instruction_path = os.path.join(TEMP_DIR, "instruction.mp3")
                self.native_path = os.path.join(TEMP_DIR, "native.mp3")
                self.image_path = os.path.join(TEMP_DIR, "image.png")

                #zipf.extract("instruction.mp3", TEMP_DIR)
                zipf.extract("native.mp3", TEMP_DIR)

                if "image.png" in zipf.namelist():
                    zipf.extract("image.png", TEMP_DIR)
                else:
                    self.image_path = ""

            self.fields["english"].delete(0, tk.END)
            self.fields["english"].insert(0, lo.english)

            self.fields["pinyin"].delete(0, tk.END)
            self.fields["pinyin"].insert(0, lo.pinyin)

            self.fields["native"].delete(0, tk.END)
            self.fields["native"].insert(0, lo.native)

            self.fields["tags"].delete(0, tk.END)
            self.fields["tags"].insert(0, ", ".join(lo.tags))

            self.fields["delay"].delete(0, tk.END)
            self.fields["delay"].insert(0, str(lo.delay_between_instruction_and_native))

            #messagebox.showinfo("Success", "File loaded. You may now edit and re-save.")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load: {e}")

    def select_instruction(self):
        initial_dir = os.path.expanduser(r"G:\Mandarin\AI Speech")
        path = filedialog.askopenfilename(initialdir=initial_dir,title="Select Instruction Audio", filetypes=[("MP3 Files", "*.mp3")])
        if path:
            self.instruction_path = path

    def select_native(self):
        initial_dir = os.path.expanduser(r"G:\Mandarin\New process")
        path = filedialog.askopenfilename(initialdir=initial_dir,title="Select Native Audio", filetypes=[("MP3 Files", "*.mp3")])
        if path:
            self.native_path = path

    def select_image(self):
        path = filedialog.askopenfilename(title="Select Image", filetypes=[("Image Files", "*.png;*.jpg;*.jpeg")])
        if path:
            self.image_path = path

    def play_instruction(self):
        if not self.instruction_path or not os.path.exists(self.instruction_path):
            messagebox.showwarning("Warning", "Instruction audio file not selected.")
            return
        pygame.mixer.music.load(self.instruction_path)
        pygame.mixer.music.play()

    def play_native(self):
        if not self.native_path or not os.path.exists(self.native_path):
            messagebox.showwarning("Warning", "Native audio file not selected.")
            return
        pygame.mixer.music.load(self.native_path)
        pygame.mixer.music.play()

    def save_learning_object(self):
        if not self.instruction_path or not self.native_path:
            messagebox.showerror("Error", "Instruction and Native audio files are required!")
            return

        try:
            english = self.fields["english"].get().strip()
            pinyin = self.fields["pinyin"].get().strip()
            native = self.fields["native"].get().strip()
            tags = [tag.strip() for tag in self.fields["tags"].get().split(",") if tag.strip()]
            delay = float(self.fields["delay"].get().strip() or "6")

            lo = LearningObjectV2(
                english=english,
                pinyin=pinyin,
                native=native,
                tags=tags,
                delay_between_instruction_and_native=delay
            )

        except Exception as e:
            messagebox.showerror("Error", f"Invalid input: {e}")
            return
        initial_dir = os.path.expanduser(r"G:\Mandarin\learning_objects - Masters")
        save_path = filedialog.asksaveasfilename(
            initialdir=initial_dir,
            title="Save LearningObject",
            defaultextension=".xue",
            filetypes=[("LearningObject Files", "*.xue")]
        )
        if not save_path:
            return

        with zipfile.ZipFile(save_path, 'w') as zipf:
            zipf.writestr("metadata.json", json.dumps(lo.to_dict(), indent=2))
            zipf.write(self.instruction_path, arcname="instruction.mp3")
            zipf.write(self.native_path, arcname="native.mp3")
            if self.image_path:
                zipf.write(self.image_path, arcname="image.png")

        #messagebox.showinfo("Success", f"LearningObject saved to {save_path}")

if __name__ == "__main__":
    root = tk.Tk()
    app = EditorApp(root)
    root.mainloop()
