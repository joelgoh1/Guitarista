import Navbar from '../components/NavBar.tsx';
import MusicXMLViewer from '../components/MusicXmlViewer.tsx';

const SongLearningPage = () => {
    return (
        <main className="page-container">
            <Navbar/>
            <div className="content-container">
                <MusicXMLViewer />
            </div>
        </main>
    );
};

export default SongLearningPage;
