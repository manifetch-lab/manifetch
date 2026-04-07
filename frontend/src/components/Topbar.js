import { useAuth } from '../context/AuthContext';
import { useLang } from '../context/LanguageContext';
import { useNavigate } from 'react-router-dom';

export default function Topbar({ title }) {
  const { user, logout } = useAuth();
  const { lang, toggle, t } = useLang();
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
        <button
          onClick={toggle}
          style={{
            background: 'rgba(255,255,255,0.15)',
            border: '1px solid rgba(255,255,255,0.3)',
            color: 'white',
            borderRadius: 6,
            padding: '3px 10px',
            fontSize: 12,
            fontWeight: 600,
            cursor: 'pointer',
            letterSpacing: '0.5px',
          }}
        >
          {lang === 'tr' ? 'EN' : 'TR'}
        </button>
        <span className="topbar-logout" onClick={handleLogout}>
          {t.topbar.logout}
        </span>
      </div>
    </div>
  );
}