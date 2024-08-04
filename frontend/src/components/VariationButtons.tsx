import React from 'react';
import styled from 'styled-components';

interface VariationButtonsProps {
  numVariations: number;
  onVariationClick: (variation: string) => void;
}

const Container = styled.div`
  display: flex;
  justify-content: center;
  margin-top: 20px;
`;

const VariationButton = styled.button`
  width: 70px;
  height: 40px;
  margin: 0 px;
  padding: 5px;
  font-size: 1em;
  cursor: pointer;
  border: 1px solid #FFF;
  background: none;
  color: #FFF;

  &:hover {
    background: #FFF;
    color: #000;
  }
`;

const VariationButtons: React.FC<VariationButtonsProps> = ({ numVariations, onVariationClick }) => {
  const buttons = Array.from({ length: numVariations }, (_, i) => (
    <VariationButton key={i} onClick={() => onVariationClick((i + 1).toString())}>
      {i + 1}
    </VariationButton>
  ));

  return <Container>{buttons}</Container>;
};

export default VariationButtons;
