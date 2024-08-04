import { guitarImg, userImg, searchImg } from '../utils';
import { navLists } from '../constants';
import { Link } from 'react-router-dom';

const Navbar = () => {
  return (
    <header className="w-full py-5 sm:px-10 px-5 flex justify-between items-center relative bg-black">
      <nav className="flex justify-between items-center w-full screen-max-width">
        
        <div className="flex items-center">
          <Link to='/' className="flex items-center">
            <img src={guitarImg} alt="Guitar" width={25} height={25} />
            <span className='text-m cursor-pointer text-gray px-5'>
              Guitarista
            </span>
          </Link>
        </div>
        
        <div className="absolute left-1/2 transform -translate-x-1/2 flex justify-center items-center">
          {navLists.map((nav) => (
            <Link key={nav.label} to={nav.path} className="px-5 text-m cursor-pointer text-gray hover:text-white transition-all">
              {nav.label}
            </Link>
          ))}
        </div>

        <div className="flex items-center gap-7">
          <img src={searchImg} alt="search" width={25} height={25} />
          <img src={userImg} alt="user" width={25} height={25} />
        </div>
      </nav>
    </header>
  )
}

export default Navbar;
