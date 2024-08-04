import Navbar from '../components/NavBar.tsx';
import { chordTypes } from '../constants/index.tsx';
import { Link, useNavigate } from 'react-router-dom';

const LearningPage = () => {
  const navigate = useNavigate();

  const handleNavigation = (chordType: string) => {
    navigate(`/chord-learning/${chordType}`);
  };

  return (
    <div>
      <Navbar />
      <div className="section-container">
        <div className="section">
          <h2 className="section-title">Chords</h2>
          <div className="boxes">
            {chordTypes.map((chord) => (
              <div
                key={chord.label}
                className="box"
                onClick={() => handleNavigation(chord.access)}
                style={{ cursor: 'pointer' }}
              >
                <h3>{chord.label}</h3>
                <p>{chord.description}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="section">
          <h2 className="section-title">Play a Song</h2>
          <div className="boxes">
            <Link className="box" to={"/song-learning"}>
              <h3>Song Mode</h3>
              <p>Learn to play along with a song.</p>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LearningPage;
