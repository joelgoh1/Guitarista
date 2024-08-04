import fluidsynth
import time

def play_chord_as_strum(notes, soundfont_path, note_duration=1.0, delay=0.1):
    """
    Plays a chord as a guitar strum.

    Parameters:
    - notes: List of MIDI pitches to be played as a strum.
    - soundfont_path: Path to the SoundFont file.
    - note_duration: Duration in seconds for each note.
    - delay: Delay in seconds between each note in the strum.
    """
    fs = fluidsynth.Synth()
    fs.start(driver="coreaudio")  # Use "alsa" for Linux, "dsound" for Windows, "coreaudio" for macOS
    sfid = fs.sfload(soundfont_path)
    fs.program_select(0, sfid, 0, 0)  # Replace with the correct bank and preset if needed

    for i, note in enumerate(notes):
        fs.noteon(0, note, 100)  # Channel 0, note, velocity 100
        time.sleep(delay)  # Delay before playing the next note

    time.sleep(note_duration)  # Wait for the duration of the note
    # Turn off all notes after the strum
    for note in notes:
        fs.noteoff(0, note)

    # Cleanup
    fs.delete()
