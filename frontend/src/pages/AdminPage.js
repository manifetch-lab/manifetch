import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Topbar from '../components/Topbar';
import { useAuth } from '../context/AuthContext';
import { useLang } from '../context/LanguageContext';
import axios from 'axios';

const BASE = 'http://127.0.0.1:8000';

export default function AdminPage() {
  const [users,   setUsers]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [form,    setForm]    = useState({ username: '', password: '', role: 'NURSE', display_name: '' });
  const [formErr, setFormErr] = useState('');
  const { user }  = useAuth();
  const { t }     = useLang();
  const navigate  = useNavigate();

  const NAV = [t.admin.userManagement, t.admin.systemSettings, t.admin.auditLogs, t.admin.dbBackup];

  useEffect(() => {
    axios.get(`${BASE}/admin/users`)
      .then(r => setUsers(r.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleAdd = async (e) => {
    e.preventDefault();
    setFormErr('');
    try {
      const res = await axios.post(`${BASE}/admin/users`, form);
      setUsers(prev => [...prev, res.data]);
      setShowAdd(false);
      setForm({ username: '', password: '', role: 'NURSE', display_name: '' });
    } catch (err) {
      setFormErr(err.response?.data?.detail || t.admin.errorAdd);
    }
  };

  const handleToggle = async (u) => {
    const endpoint = u.is_active ? 'deactivate' : 'activate';
    try {
      await axios.patch(`${BASE}/admin/users/${u.user_id}/${endpoint}`);
      setUsers(prev => prev.map(x => x.user_id === u.user_id ? { ...x, is_active: !x.is_active } : x));
    } catch (err) {
      alert(err.response?.data?.detail || 'İşlem başarısız.');
    }
  };

  return (
    <div>
      <Topbar title={t.admin.title} />
      <div style={{ display: 'flex', minHeight: 'calc(100vh - 56px)' }}>
        <div style={{ width: 220, background: 'var(--navy)', padding: '24px 0', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {NAV.map((item, i) => (
            <button key={item} style={{
              background: i === 0 ? 'var(--teal)' : 'transparent',
              color: i === 0 ? 'white' : 'rgba(255,255,255,0.7)',
              border: 'none', padding: '12px 20px', textAlign: 'left', fontSize: 14, cursor: 'pointer',
            }}>
              {item}
            </button>
          ))}
        </div>

        <div className="page-content" style={{ flex: 1 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <h2 style={{ color: 'var(--navy)', fontSize: 22, fontWeight: 700 }}>{t.admin.userManagement}</h2>
            <button className="btn btn-primary" onClick={() => setShowAdd(true)}>{t.admin.addUser}</button>
          </div>

          {showAdd && (
            <div className="card" style={{ marginBottom: 20 }}>
              <h3 style={{ marginBottom: 16, color: 'var(--navy)' }}>{t.admin.newUser}</h3>
              <form onSubmit={handleAdd}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 16 }}>
                  <div className="form-group" style={{ margin: 0 }}>
                    <label className="form-label">{t.admin.username}</label>
                    <input className="form-input" value={form.username}
                      onChange={e => setForm(f => ({ ...f, username: e.target.value }))} required />
                  </div>
                  <div className="form-group" style={{ margin: 0 }}>
                    <label className="form-label">{t.admin.password}</label>
                    <input className="form-input" type="password" value={form.password}
                      onChange={e => setForm(f => ({ ...f, password: e.target.value }))} required />
                  </div>
                  <div className="form-group" style={{ margin: 0 }}>
                    <label className="form-label">{t.admin.displayName}</label>
                    <input className="form-input" value={form.display_name}
                      onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))} required />
                  </div>
                  <div className="form-group" style={{ margin: 0 }}>
                    <label className="form-label">{t.admin.role}</label>
                    <select className="form-input" value={form.role}
                      onChange={e => setForm(f => ({ ...f, role: e.target.value }))}>
                      <option value="NURSE">Nurse</option>
                      <option value="DOCTOR">Doctor</option>
                      <option value="ADMINISTRATOR">Administrator</option>
                    </select>
                  </div>
                </div>
                {formErr && <p className="error-msg" style={{ marginTop: 8 }}>{formErr}</p>}
                <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
                  <button className="btn btn-primary" type="submit">{t.admin.save}</button>
                  <button className="btn btn-outline" type="button" onClick={() => setShowAdd(false)}>{t.admin.cancel}</button>
                </div>
              </form>
            </div>
          )}

          <div className="table-wrapper" style={{ marginBottom: 20 }}>
            {loading ? (
              <div className="loading"><div className="spinner" />{t.admin.loading}</div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>{t.admin.usernameCol}</th>
                    <th>{t.admin.fullName}</th>
                    <th>{t.admin.roleCol}</th>
                    <th>{t.admin.status}</th>
                    <th>{t.admin.actions}</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map(u => (
                    <tr key={u.user_id}>
                      <td style={{ fontFamily: 'DM Mono, monospace', fontSize: 13 }}>{u.username}</td>
                      <td style={{ fontWeight: 500 }}>{u.display_name}</td>
                      <td>{u.role}</td>
                      <td><span className={u.is_active ? 'status-stable' : 'status-inactive'}>
                        {u.is_active ? t.admin.active : t.admin.inactive}
                      </span></td>
                      <td>
                        <button
                          className={`btn ${u.is_active ? 'btn-danger' : 'btn-primary'}`}
                          style={{ padding: '3px 12px', fontSize: 12 }}
                          onClick={() => handleToggle(u)}
                          disabled={u.user_id === user?.user_id}
                        >
                          {u.is_active ? t.admin.deactivate : t.admin.activate}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="card">
            <h3 style={{ color: 'var(--navy)', marginBottom: 12 }}>{t.admin.rolesTitle}</h3>
            {Object.entries(t.admin.roles).map(([role, desc]) => (
              <p key={role} style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 8 }}>
                <strong style={{ color: 'var(--text)' }}>{role.charAt(0) + role.slice(1).toLowerCase()}:</strong> {desc}
              </p>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}