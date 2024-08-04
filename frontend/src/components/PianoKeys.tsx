import React from 'react';
import styled from 'styled-components';
import pianoImage from '/assets/images/pianoKeys.png';
import { pianoPositionMap } from '../utils/positionMappings';

interface PianoKeysProps {
  notes: string[];
}

const PianoContainer = styled.div`
  position: relative;
  width: 100%;
  max-width: 1000px;
  margin: 0 auto; /* Center the image */
`;

const PianoImage = styled.img`
  width: 100%;
  height: auto;
`;

const NoteCircle = styled.div<{ top: number; left: number }>`
  position: absolute;
  top: ${(props) => props.top}%;
  left: ${(props) => props.left}%;
  width: 35px;
  height: 35px;
  border-radius: 50%;
  background-color: green;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: bold;
`;

const PianoKeys: React.FC<PianoKeysProps> = ({ notes }) => {
  return (
    <PianoContainer>
      <PianoImage src={pianoImage} alt="Piano Keys" />
      {notes.map((note, index) => {
        const position = pianoPositionMap[note];
        if (!position) return null;
        return (
          <NoteCircle
            key={index}
            top={position.top}
            left={position.left}
          >
            {note}
          </NoteCircle>
        );
      })}
    </PianoContainer>
  );
};

export default PianoKeys;
