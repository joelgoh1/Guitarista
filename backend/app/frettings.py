from music21 import note, converter, articulations, stream

def calculate_fret_positions(target_note, tuning):
    note_frets = {}
    target_pitch = target_note.pitch.midi  # Get the MIDI number of the target note

    for base_string, open_note in enumerate(tuning, start=1):
        open_pitch = open_note.pitch.midi  # MIDI number of the open string note
        semitone_diff = target_pitch - open_pitch  # Calculate the difference in semitones
        
        if 0 <= semitone_diff <= 19:  # Check if the note is within the fret range
            note_frets.setdefault(target_note.nameWithOctave, []).append((base_string, semitone_diff))

    return note_frets

def choose_optimal_fingering(notes, tuning):
    previous_fingering = None
    optimal_fingerings = []

    for n in notes:
        # Calculate possible fret positions for each note
        fret_positions = calculate_fret_positions(n, tuning)

        if not fret_positions:
            optimal_fingerings.append((n, None))
            continue

        # Choose the fingering that minimizes hand movement
        best_fingering = None
        min_distance = float('inf')

        for pos in fret_positions.get(n.nameWithOctave, []):
            if previous_fingering is None:
                best_fingering = pos
                break  # No previous fingering, choose the first available
            
            # Calculate distance: sum of absolute differences in string and fret positions
            string_dist = abs(previous_fingering[0] - pos[0])
            fret_dist = abs(previous_fingering[1] - pos[1])
            distance = string_dist + fret_dist

            if distance < min_distance:
                min_distance = distance
                best_fingering = pos

        optimal_fingerings.append((n, best_fingering))
        previous_fingering = best_fingering

    return optimal_fingerings

# Load a MusicXML file and parse notes
score = converter.parse('/Users/joel/Documents/Projs/Guitarista/backend/assets/musescore/twinkle.musicxml')
notes = [n for n in score.flat.notes if isinstance(n, note.Note)]

# Define the guitar tuning
tuning_notes = [note.Note(n) for n in ['E4', 'B3', 'G3', 'D3', 'A2', 'E2']]

# Get optimal fingerings
optimal_fingerings = choose_optimal_fingering(notes, tuning_notes)

# Append the fingerings to the MusicXML file
for note_obj, fingering in optimal_fingerings:
    if fingering:
        string, fret = fingering
        string_indication = articulations.StringIndication(string)
        fret_indication = articulations.FretIndication(fret)
        note_obj.articulations.append(string_indication)
        note_obj.articulations.append(fret_indication)

# Save the modified score to a new MusicXML file
new_filename = '/Users/joel/Documents/Projs/Guitarista/backend/assets/musescore/twinkle_with_fingerings.musicxml'
score.write('musicxml', fp=new_filename)

print(f"Fingerings appended and saved to {new_filename}")
