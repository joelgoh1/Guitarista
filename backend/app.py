from flask import Flask, request, jsonify
from flask_cors import CORS
from app import PlayChord  # Assuming PlayChord is the main class in playchord.py
from utils import note_name_to_midi

app = Flask(__name__)
CORS(app)

@app.route('/api/play', methods=['POST'])
def play():
    data = request.get_json()
    note_names = data.get('notes', [])
    soundfont_path = "/Users/joel/Documents/Projs/Guitarista/backend/assets/soundfont/Soundtrap_Clean_Guitar.sf2" 

    # Convert note names to MIDI pitches
    notes = [note_name_to_midi(note_name) for note_name in note_names]

    PlayChord.play_chord_as_strum(notes, soundfont_path)  # Assuming play_chord_as_strum is a static method or class method
    return jsonify({"status": "success", "message": "Notes are being played"})

if __name__ == '__main__':
    app.run(debug=True)