import React from 'react';
import styled from 'styled-components';
import { Link } from 'react-router-dom';

const Section = styled.section`
  padding: 20px;
  border-bottom: 1px solid #eee;
`;

const SectionTitle = styled.h2`
  font-size: 1.8em;
  margin-bottom: 10px;
`;

const SectionContent = styled.div`
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
`;

const Feature = styled.div`
  flex: 1 1 calc(33.333% - 40px);
  padding: 20px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
`;

const FeatureSection: React.FC = () => {
  return (
    <Section>
      <SectionTitle>Learn Guitar Chords</SectionTitle>
      <SectionContent>
        <Feature>
          <Link to="/chord-learning">
            <h3>Interactive Lessons</h3>
            <p>Learn and practice chords interactively.</p>
          </Link>
        </Feature>
        <Feature>
          <h3>Training</h3>
          <p>Get tested on chords with real-time feedback.</p>
        </Feature>
        <Feature>
          <h3>Tabgen</h3>
          <p>Upload musicXML scores and generate tabs.</p>
        </Feature>
        <Feature>
          <h3>Achievements</h3>
          <p>Track your progress and earn achievements.</p>
        </Feature>
        <Feature>
          <h3>Progress</h3>
          <p>See how much you have learned over time.</p>
        </Feature>
        <Feature>
          <h3>Library</h3>
          <p>Access a library of songs and exercises.</p>
        </Feature>
        <Feature>
          <h3>Profile</h3>
          <p>Manage your profile and settings.</p>
        </Feature>
        <Feature>
          <h3>Game</h3>
          <p>Play games to improve your skills.</p>
        </Feature>
      </SectionContent>
    </Section>
  );
};

export default FeatureSection;
