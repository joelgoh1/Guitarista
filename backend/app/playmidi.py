import music21
import fluidsynth
import mido
import os

def add_metronome_count_in(score, bpm, count_measures=1):
    """
    Adds a count-in metronome at the beginning of the score.
    """
    metronome_part = music21.stream.Part()
    metronome_instrument = music21.instrument.Woodblock()
    metronome_part.insert(0, metronome_instrument)

    metronome_tempo = music21.tempo.MetronomeMark(number=bpm)
    metronome_part.insert(0, metronome_tempo)

    for _ in range(count_measures):
        measure = music21.stream.Measure()
        for beat in range(4):  # Assuming 4/4 time signature
            if beat == 0:
                click = music21.note.Note("C5", quarterLength=1)  # Strong beat
            else:
                click = music21.note.Note("C4", quarterLength=1)  # Weak beats
            measure.append(click)
        metronome_part.append(measure)

    score.insert(0, metronome_part)

def add_metronome_track(score, bpm):
    """
    Adds a metronome track that plays together with the score.
    """
    metronome_part = music21.stream.Part()
    metronome_instrument = music21.instrument.Woodblock()
    metronome_part.insert(0, metronome_instrument)

    metronome_tempo = music21.tempo.MetronomeMark(number=bpm)
    metronome_part.insert(0, metronome_tempo)

    for measure in score.parts[0].measures(1, None):
        metronome_measure = music21.stream.Measure()
        for beat in range(4):  # Assuming 4/4 time signature
            if beat == 0:
                click = music21.note.Note("C5", quarterLength=1)  # Strong beat
            else:
                click = music21.note.Note("C4", quarterLength=1)  # Weak beats
            metronome_measure.append(click)
        metronome_part.append(metronome_measure)

    score.insert(0, metronome_part)

def extract_measures(score, start_measure=None, end_measure=None):
    parts = music21.stream.Score()
    last_tempo = None  # Variable to store the last encountered tempo mark
    for part in score.parts:
        extracted_part = music21.stream.Part()
        for measure in part.getElementsByClass('Measure'):
            # Store the last encountered MetronomeMark
            for element in measure.elements:
                if isinstance(element, music21.tempo.MetronomeMark):
                    last_tempo = element
            # Extract measures within the specified range
            if (start_measure is None or measure.number >= start_measure) and (end_measure is None or measure.number <= end_measure):
                if start_measure is not None and measure.number == start_measure and last_tempo is not None:
                    extracted_part.append(last_tempo)  # Append the last tempo mark to the start measure
                extracted_part.append(measure)
        parts.append(extracted_part)
    return parts

def set_instruments(score):
    for part in score.parts:
        # Set the instrument for the part
        instrument = music21.instrument.fromString('Acoustic Guitar (nylon)')  # Change to the desired instrument
        part.insert(0, instrument)
    return score

def add_tempo_mark(score, new_bpm):
    tempo = music21.tempo.MetronomeMark(number=new_bpm)
    score.insert(0, tempo)
    return score

def convert_to_midi(score, midi_path, new_bpm=None):
    try:
        if new_bpm:
            # Change the tempo
            for element in score.flat.getElementsByClass(music21.tempo.MetronomeMark):
                element.number = new_bpm

        # Set instruments
        score = set_instruments(score)
        
        mf = music21.midi.translate.music21ObjectToMidiFile(score)
        mf.open(midi_path, 'wb')
        mf.write()
        mf.close()
    except Exception as e:
        print(f"Error converting MusicXML to MIDI: {e}")

def play_midi(midi_path, soundfont_path, loop=False):
    def play_once():
        try:
            fs = fluidsynth.Synth()
            fs.start(driver="coreaudio")  # Change driver if needed for your system
            sfid = fs.sfload(soundfont_path)
            
            midi_file = mido.MidiFile(midi_path)
            
            for msg in midi_file.play():
                if msg.type == 'note_on':
                    fs.noteon(msg.channel, msg.note, msg.velocity)
                elif msg.type == 'note_off':
                    fs.noteoff(msg.channel, msg.note)
                elif msg.type == 'control_change':
                    fs.cc(msg.channel, msg.control, msg.value)
                elif msg.type == 'program_change':
                    fs.program_select(msg.channel, sfid, 0, 0)
                elif msg.type == 'set_tempo':
                    tempo = mido.tempo2bpm(msg.tempo)
                    print(f"Set tempo to: {tempo} BPM")
            
            fs.delete()
        except Exception as e:
            print(f"Error playing MIDI file: {e}")

    if loop:
        for _ in range(15):
            play_once()
    else:
        play_once()

if __name__ == "__main__":
    musicxml_path = '/Users/joel/Documents/Projs/Guitarista/backend/assets/musescore/Crepe_a2.musicxml'
    midi_path = 'assets/temp/midi/file.mid'
    soundfont_path = '/Users/joel/Documents/Projs/Guitarista/backend/assets/soundfont/yahoo.sf2'
    new_bpm = 300
    start_measure = 82
    end_measure = 97

    if not os.path.exists(musicxml_path):
        print(f"MusicXML file not found: {musicxml_path}")
    elif not os.path.exists(soundfont_path):
        print(f"SoundFont file not found: {soundfont_path}")
    else:
        score = music21.converter.parse(musicxml_path)
        if start_measure or end_measure:
            score = extract_measures(score, start_measure, end_measure)

        convert_to_midi(score, midi_path, new_bpm)
        if os.path.exists(midi_path):
            play_midi(midi_path, soundfont_path, loop=True)
        else:
            print(f"Failed to create MIDI file: {midi_path}")
