Recorded 2026-09-11 from the live (unofficial) Songsterr API, Oasis – Wonderwall (songId 2, revisionId 8047059, image v0-3-2-hmpMBN-NNIVq9p59).

- songs_search.json  ← GET https://www.songsterr.com/api/songs?pattern=oasis%20wonderwall
- meta_2.json        ← GET https://www.songsterr.com/api/meta/2
- track_2_3.json     ← GET https://dqsljvtekg760.cloudfront.net/2/8047059/v0-3-2-hmpMBN-NNIVq9p59/3.json (rhythm guitar; gzip-encoded on the wire)
- track_2_6.json     ← same, track 6 (bass)

Observed track shape: top-level `name, capo, frets, tuning[high→low MIDI], strings, instrumentId, instrument,
automations.tempo[{type, position, measure, bpm}], measures[{signature?, marker?{text}, voices[{beats[]}]}]`.
Beat: `notes[{string (0 = highest), fret, tie?, rest?}], type (1,2,4,8,16,32 note type), duration [num, den],
rest?, velocity?, letRing?, chord?{text}, beamStart/beamStop, dotted?`.
