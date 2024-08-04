import React from 'react';
import styled from 'styled-components';
import neckImage from '/assets/images/guitarNeck.png';
import { guitarPositionMap } from '../utils/positionMappings';

interface FingerPosition {
  string: number;
  fret: number;
  finger: number;
}

interface Bar {
  hasBar: boolean;
  top: number;
  bottom: number;
  fret: number;
}

interface ChordData {
  positions: FingerPosition[];
  bar: Bar;
}

interface ChordDiagramProps {
  chordData: ChordData;
}

const Container = styled.div`
  position: relative;
  width: 100%;
  max-width: 1000px;
`;

const NeckImage = styled.img`
  width: 100%;
  height: auto;
`;

const PositionCircle = styled.div<{ top: number; left: number }>`
  position: absolute;
  top: ${(props) => props.top}%;
  left: ${(props) => props.left}%;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background-color: orange;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
`;

const PositionBar = styled.div<{ top1: number; strings: number; left: number }>`
  position: absolute;
  top: ${(props) => props.top1}%;
  left: ${(props) => props.left}%;
  height: ${(props) => 13 * props.strings}%;
  width: 30px;
  border-radius: 15px;
  background-color: orange;
`;

const DiagramContainer = styled.div`
  position: relative;
`;

const ChordDiagram: React.FC<ChordDiagramProps> = ({ chordData }) => {
  const { positions, bar } = chordData;

  return (
    <Container>
      <DiagramContainer>
        <NeckImage src={neckImage} alt="Guitar Neck" />
        {bar.hasBar && (
          <PositionBar
            top1={guitarPositionMap[`${bar.top}_1`].top}
            strings={bar.bottom - bar.top + 1}
            left={guitarPositionMap[`1_${bar.fret}`].left}
          />
        )}
        {positions.map((pos, index) => {
          const key = `${pos.string}_${pos.fret}`;
          const position = guitarPositionMap[key];
          if (!position) return null;
          return (
            <PositionCircle
              key={index}
              top={position.top}
              left={position.left}
            >
              {pos.finger}
            </PositionCircle>
          );
        })}
      </DiagramContainer>
    </Container>
  );
};

export default ChordDiagram;
