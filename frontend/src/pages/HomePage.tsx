import Navbar from '../components/NavBar.tsx';
import Hero from '../components/Hero';
import Footer from '../components/Footer';

const HomePage: React.FC = () => {
    return (
        <main className="bg-black">
        <Navbar />
        <Hero />
        <Footer />
      </main>
    );
  };
  
  export default HomePage;
  