from music21 import note

def replace_custom_symbols(note_name):
    """
    Replaces custom sharp and flat symbols with the standard ones used by music21.

    Parameters:
    - note_name: The note name as a string (e.g., C♯5, E♭4).

    Returns:
    - The note name with standard sharp and flat symbols (e.g., C#5, E-4).
    """
    return note_name.replace('♯', '#').replace('♭', '-')

def note_name_to_midi(note_name):
    """
    Converts a note name (e.g., C#5) to its corresponding MIDI pitch using music21.

    Parameters:
    - note_name: The note name as a string (e.g., C#5, E-4).

    Returns:
    - The corresponding MIDI pitch as an integer.
    """
    standard_note_name = replace_custom_symbols(note_name)
    return note.Note(standard_note_name).pitch.midi
