import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';

export default function Topbar({ title }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="topbar">
      <span className="topbar-title">{title || 'Manifetch NICU'}</span>
      <div className="topbar-user">
        <span>{user?.display_name}</span>
        <span className="topbar-logout" onClick={handleLogout}>Logout</span>
      </div>
    </div>
  );
}