import React, { useState, useRef, useEffect } from 'react';
import { OpenSheetMusicDisplay } from 'opensheetmusicdisplay';

const MusicXMLViewer = () => {
    const [musicXml, setMusicXml] = useState<string>('');
    const [bpm, setBpm] = useState<number>(120);
    const osmdRef = useRef<any>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const websocketRef = useRef<WebSocket | null>(null);

    useEffect(() => {
        if (musicXml) {
            renderScore();
        }
    }, [musicXml]);

    useEffect(() => {
        websocketRef.current = new WebSocket('ws://localhost:8765');
        websocketRef.current.onmessage = handleWebSocketMessage;
        return () => {
            if (websocketRef.current) {
                websocketRef.current.close();
            }
        };
    }, []);

    const handleWebSocketMessage = (event: MessageEvent) => {
        const data = JSON.parse(event.data);
        if (data.type === 'start') {
            setBpm(parseFloat(data.bpm));
        } else if (data.type === 'note_on') {
            highlightNote(data.note);
        }
    };

    const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files ? event.target.files[0] : null;
        if (file) {
            const reader = new FileReader();
            reader.onload = (e) => {
                const text = e.target?.result;
                setMusicXml(text as string);
            };
            reader.readAsText(file);
        }
    };

    const renderScore = () => {
        if (containerRef.current) {
            const osmd = new OpenSheetMusicDisplay(containerRef.current, {
                autoResize: true,
                drawFromMeasureNumber: 1,
                drawUpToMeasureNumber: Number.MAX_SAFE_INTEGER,
                drawTitle: true,
            });
            osmd.load(musicXml).then(() => {
                osmd.render();
                osmdRef.current = osmd;
            });
        }
    };

    const highlightNote = (midiPitch: number) => {
        if (osmdRef.current) {
            const osmd = osmdRef.current;
            osmd.drawer.clear();
            osmd.render();
            
            const allNotes = osmd.GraphicSheet.MeasureList.flatMap((measure: { staffEntries: { graphicalVoiceEntries: any[]; }[]; }) => 
                measure.staffEntries.flatMap((staffEntry: { graphicalVoiceEntries: any[]; }) => 
                    staffEntry.graphicalVoiceEntries.flatMap(voice => 
                        voice.notes
                    )
                )
            );
            
            const noteToHighlight = allNotes.find((note: { sourceMeasure: { NotesWithPitch: { halfTone: number; }[]; }; }) => note.sourceMeasure.NotesWithPitch[0].halfTone === midiPitch);
            
            if (noteToHighlight) {
                osmd.GraphicSheet.DrawOverlayLine(noteToHighlight.sourceNote.NoteheadBoundingBox, "red");
            }
        }
    };

    const handlePlay = () => {
        if (websocketRef.current && websocketRef.current.readyState === WebSocket.OPEN) {
            websocketRef.current.send(JSON.stringify({
                action: 'play',
                musicxml_path: 'path/to/your/musicxml/file.xml',  // You need to provide the actual path
                bpm: bpm
            }));
        }
    };

    return (
        <div className="musicxml-viewer">
            <input type="file" accept=".xml,.musicxml" onChange={handleFileChange} />
            <button className={'bg-black'} onClick={handlePlay}>Play</button>
            <div ref={containerRef} className="musicxml-container" />
        </div>
    );
};

export default MusicXMLViewer;