import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Topbar from '../components/Topbar';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';

const BASE = 'http://127.0.0.1:8000';
const NAV  = ['User Management', 'System Settings', 'Audit Logs', 'Database Backup'];

const ROLE_DESC = {
  ADMINISTRATOR: 'Full system access, user management, configuration',
  DOCTOR:        'View/edit patient data, generate reports, access AI results',
  NURSE:         'Monitor patients, acknowledge alerts, update vital signs',
};

export default function AdminPage() {
  const [users,   setUsers]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [form,    setForm]    = useState({ username: '', password: '', role: 'NURSE', display_name: '' });
  const [formErr, setFormErr] = useState('');
  const { user }   = useAuth();
  const navigate   = useNavigate();

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
      setFormErr(err.response?.data?.detail || 'Kullanıcı eklenemedi.');
    }
  };

  const handleToggle = async (u) => {
    const endpoint = u.is_active ? 'deactivate' : 'activate';
    try {
      await axios.patch(`${BASE}/admin/users/${u.user_id}/${endpoint}`);
      setUsers(prev => prev.map(x =>
        x.user_id === u.user_id ? { ...x, is_active: !x.is_active } : x
      ));
    } catch (err) {
      alert(err.response?.data?.detail || 'İşlem başarısız.');
    }
  };

  return (
    <div>
      <Topbar title="Administration Panel" />
      <div style={{ display: 'flex', minHeight: 'calc(100vh - 56px)' }}>
        {/* Sidebar */}
        <div style={{
          width: 220, background: 'var(--navy)', padding: '24px 0',
          display: 'flex', flexDirection: 'column', gap: 4,
        }}>
          {NAV.map((item, i) => (
            <button key={item} style={{
              background: i === 0 ? 'var(--teal)' : 'transparent',
              color: i === 0 ? 'white' : 'rgba(255,255,255,0.7)',
              border: 'none', padding: '12px 20px', textAlign: 'left',
              fontSize: 14, cursor: 'pointer', transition: 'all 0.15s',
            }}>
              {item}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="page-content" style={{ flex: 1 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <h2 style={{ color: 'var(--navy)', fontSize: 22, fontWeight: 700 }}>User Management</h2>
            <button className="btn btn-primary" onClick={() => setShowAdd(true)}>+ Add User</button>
          </div>

          {/* Add user form */}
          {showAdd && (
            <div className="card" style={{ marginBottom: 20 }}>
              <h3 style={{ marginBottom: 16, color: 'var(--navy)' }}>New User</h3>
              <form onSubmit={handleAdd}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 16 }}>
                  <div className="form-group" style={{ margin: 0 }}>
                    <label className="form-label">Username</label>
                    <input className="form-input" value={form.username}
                      onChange={e => setForm(f => ({ ...f, username: e.target.value }))} required />
                  </div>
                  <div className="form-group" style={{ margin: 0 }}>
                    <label className="form-label">Password</label>
                    <input className="form-input" type="password" value={form.password}
                      onChange={e => setForm(f => ({ ...f, password: e.target.value }))} required />
                  </div>
                  <div className="form-group" style={{ margin: 0 }}>
                    <label className="form-label">Display Name</label>
                    <input className="form-input" value={form.display_name}
                      onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))} required />
                  </div>
                  <div className="form-group" style={{ margin: 0 }}>
                    <label className="form-label">Role</label>
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
                  <button className="btn btn-primary" type="submit">Save</button>
                  <button className="btn btn-outline" type="button" onClick={() => setShowAdd(false)}>Cancel</button>
                </div>
              </form>
            </div>
          )}

          {/* Users table */}
          <div className="table-wrapper" style={{ marginBottom: 20 }}>
            {loading ? (
              <div className="loading"><div className="spinner" />Loading users...</div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Username</th>
                    <th>Full Name</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map(u => (
                    <tr key={u.user_id}>
                      <td style={{ fontFamily: 'DM Mono, monospace', fontSize: 13 }}>{u.username}</td>
                      <td style={{ fontWeight: 500 }}>{u.display_name}</td>
                      <td>{u.role}</td>
                      <td>
                        <span className={u.is_active ? 'status-stable' : 'status-inactive'}>
                          {u.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td>
                        <button
                          className={`btn ${u.is_active ? 'btn-danger' : 'btn-primary'}`}
                          style={{ padding: '3px 12px', fontSize: 12 }}
                          onClick={() => handleToggle(u)}
                          disabled={u.user_id === user?.user_id}
                        >
                          {u.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Role permissions */}
          <div className="card">
            <h3 style={{ color: 'var(--navy)', marginBottom: 12 }}>Role Permissions Overview</h3>
            {Object.entries(ROLE_DESC).map(([role, desc]) => (
              <p key={role} style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 8 }}>
                <strong style={{ color: 'var(--text)' }}>
                  {role.charAt(0) + role.slice(1).toLowerCase()}:
                </strong> {desc}
              </p>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}