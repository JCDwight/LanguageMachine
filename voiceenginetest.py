import pyttsx3
engine = pyttsx3.init(driverName='espeak')
voices = engine.getProperty('voices')
print("Voices found:", len(voices))
for v in voices:
    print(v.name)