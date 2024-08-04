import React from 'react';
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';
import HomePage from './pages/HomePage';
import ChordLearningPage from './pages/ChordLearningPage';
import LearningPage from './pages/LearningPage';
import SongLearningPage from './pages/SongLearningPage';

const App: React.FC = () => {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/learning" element={<LearningPage />} />
        <Route path="/chord-learning/:chordType" element={<ChordLearningPage />} />
        <Route path="/song-learning" element={<SongLearningPage />} />
      </Routes>
    </Router>
  );
};

export default App;
