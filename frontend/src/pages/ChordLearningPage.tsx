import React, { useState, useEffect, useCallback } from 'react';
import axiosInstance from '../api/axios';
import styled from 'styled-components';
import ChordDiagram from '../components/ChordDiagram';
import PianoKeys from '../components/PianoKeys';
import VariationButtons from '../components/VariationButtons';
import { FaArrowLeft, FaArrowRight, FaImage, FaLightbulb } from 'react-icons/fa';
import Navbar from '../components/NavBar.tsx';
import { useParams } from 'react-router-dom';
import { chordKeyArray } from '../constants/index.tsx';

const ChordName = styled.h1`
  font-size: 2em;
  margin: 10px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
`;

const NavigationContainer = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 40px 0;
`;

const ArrowButton = styled.button`
  background: none;
  border: none;
  cursor: pointer;
  font-size: 3em;
  color: #FFF;
  margin: 0 20px;
`;

const IconButton = styled.button`
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1.5em;
  color: #FFF;
  margin: 0 10px;
`;

const ButtonContainer = styled.div`
  display: flex;
  justify-content: center;
  gap: 10px;
  margin: 20px 0;
`;

const Button = styled.button`
  padding: 10px 20px;
  font-size: 1em;
  cursor: pointer;
`;

interface ChordData {
  notes: string[];
  positions: { string: number; fret: number; finger: number }[];
  bar: { hasBar: boolean; top: number; bottom: number; fret: number };
}

interface ChordKeyData {
  name: string;
  num_variations: number;
  variations: { [key: string]: ChordData };
}

const ChordLearningPage: React.FC = () => {
  const { chordType } = useParams<{ chordType: string }>();
  const [chordData, setChordData] = useState<ChordData | null>(null);
  const [chordKeyData, setChordKeyData] = useState<ChordKeyData | null>(null);
  const [idx, setIdx] = useState(0);
  const [chordKey, setChordKey] = useState(chordKeyArray[idx]);
  const [fetchedData, setFetchedData] = useState<{ [key: string]: ChordKeyData } | null>(null);
  const [selectedVariation, setSelectedVariation] = useState('1')
  
  const changeChord = useCallback((chordKey: string, variation: string) => {
    if (fetchedData) {
      const chord = fetchedData[chordKey];
      setChordKeyData(chord);
      console.log(chordKeyData);
      if (chord && chord.variations && chord.variations[variation]) {
        const selectedChordData = { ...chord.variations[variation] };
        setChordData(selectedChordData);
      } else {
        console.error('Chord or variation not found in data');
      }
    }
  }, [fetchedData]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch(`/data/chords/${chordType}Chords.json`);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data: { [key: string]: ChordKeyData } = await response.json();
        setFetchedData(data);
        changeChord(chordKey, selectedVariation);
      } catch (error) {
        console.error('Error fetching data:', error);
      }
    };

    fetchData();
  }, [chordType, chordKey, changeChord]);

  const handlePlayChord = () => {
    axiosInstance.post('play', { notes: chordData ? chordData.notes : [] });
  };

  const handleTryChord = () => {
    // Logic to let user try the chord and give feedback
  };

  const handleNextChord = () => {
    setIdx((prevIdx) => {
      const newIndex = (prevIdx + 1) % chordKeyArray.length;
      const newChordKey = chordKeyArray[newIndex];
      setChordKey(newChordKey);
      setSelectedVariation('1');
      changeChord(newChordKey, selectedVariation);
      return newIndex;
    });
  };
  
  const handlePreviousChord = () => {
    setIdx((prevIdx) => {
      const newIndex = (prevIdx - 1 + chordKeyArray.length) % chordKeyArray.length;
      const newChordKey = chordKeyArray[newIndex];
      setChordKey(newChordKey);
      setSelectedVariation('1');
      changeChord(newChordKey, selectedVariation);
      return newIndex;
    });
  };

  const handleVariationClick = (variation: string) => {
    setSelectedVariation(variation);
    changeChord(chordKey, variation);
  };

  if (!chordData || !chordKeyData) {
    return <div>Loading...</div>;
  }

  return (
    <>
      <Navbar />
      <ChordName>{chordKeyData.name}</ChordName>
      <NavigationContainer>
        <ArrowButton onClick={handlePreviousChord}>
          <FaArrowLeft />
        </ArrowButton>
        <ChordDiagram chordData={chordData} />
        <ArrowButton onClick={handleNextChord}>
          <FaArrowRight />
        </ArrowButton>
      </NavigationContainer>
      <PianoKeys notes={chordData.notes} />
      <ButtonContainer>
        <IconButton>
          <FaImage />
        </IconButton>
        <Button onClick={handlePlayChord}>Play Audio</Button>
        <Button onClick={handleTryChord}>Test and get feedback</Button>
        <IconButton>
          <FaLightbulb />
        </IconButton>
      </ButtonContainer>
      <VariationButtons numVariations={chordKeyData.num_variations} onVariationClick={handleVariationClick} />
    </>
  );
};

export default ChordLearningPage;
