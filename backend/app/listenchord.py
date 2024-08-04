import numpy as np
import pyaudio
from scipy.signal import butter, lfilter, find_peaks
from scipy.fft import fft, fftfreq
from music21 import note

def note_name_to_freq(note_name):
    """
    Converts a note name (e.g., C#5) to its corresponding frequency in Hz using music21.

    Parameters:
    - note_name: The note name as a string (e.g., C#5, E-4).

    Returns:
    - The corresponding frequency in Hz.
    """
    n = note.Note(note_name)
    return n.pitch.frequency

def bandpass_filter(data, lowcut, highcut, fs, order=5):
    nyquist = 0.5 * fs
    low = lowcut / nyquist
    high = highcut / nyquist
    b, a = butter(order, [low, high], btype='band')
    y = lfilter(b, a, data)
    return y

def record_audio(duration, fs=44100, channels=1):
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paFloat32,
                    channels=channels,
                    rate=fs,
                    input=True,
                    frames_per_buffer=1024)

    print("Recording...")
    frames = []

    for _ in range(0, int(fs / 1024 * duration)):
        data = stream.read(1024)
        frames.append(np.frombuffer(data, dtype=np.float32))

    print("Recording finished.")

    stream.stop_stream()
    stream.close()
    p.terminate()

    return np.hstack(frames)

def detect_chord(notes, duration=5, fs=44100, lowcut=50, highcut=1500):
    expected_freqs = [note_name_to_freq(note) for note in notes]
    audio = record_audio(duration, fs)
    filtered_audio = audio

    N = len(filtered_audio)
    T = 1.0 / fs
    yf = fft(filtered_audio)
    xf = fftfreq(N, T)[:N//2]

    amplitudes = 2.0/N * np.abs(yf[:N//2])
    peaks, _ = find_peaks(amplitudes, height=0.5)  # Adjust height as needed

    print(peaks)

    detected_freqs = xf[peaks]
    detected_amplitudes = amplitudes[peaks]

    results = analyze_frequencies(detected_freqs, detected_amplitudes, expected_freqs)
    return results

def analyze_frequencies(detected_freqs, detected_amplitudes, expected_freqs, tolerance=1.5):
    feedback = []
    detected_notes = []
    print(detected_freqs)

    for freq in detected_freqs:
        closest_note = min(expected_freqs, key=lambda x: abs(x - freq))
        if abs(closest_note - freq) < tolerance:
            detected_notes.append(closest_note)
        else:
            feedback.append(f"Unexpected frequency detected: {freq:.2f} Hz")

    print(detected_notes)

    for expected_freq in expected_freqs:
        if expected_freq not in detected_notes:
            feedback.append(f"Note {note.Note()} was not detected clearly.")

    if not feedback:
        feedback.append("Good job! All notes were detected clearly.")

    return feedback

def main():
    notes = ["C3", "E3", "G3", "C4", "E4"] # Example notes
    feedback = detect_chord(notes)
    for message in feedback:
        print(message)

if __name__ == "__main__":
    main()
