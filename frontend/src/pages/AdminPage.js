import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Topbar from '../components/Topbar';
import { useAuth } from '../context/AuthContext';
import { useLang } from '../context/LanguageContext';
import { api } from '../api/client';
import axios from 'axios';

const BASE = process.env.REACT_APP_API_URL || 'http://127.0.0.1:8000';

export default function AdminPage() {
  const [users,       setUsers]       = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [showAdd,     setShowAdd]     = useState(false);
  const [activeNav,   setActiveNav]   = useState(0);
  const [form,        setForm]        = useState({ username: '', password: '', role: 'NURSE', display_name: '' });
  const [formErr,     setFormErr]     = useState('');
  const [patients,    setPatients]    = useState([]);
  const [simPatient,  setSimPatient]  = useState('');
  const [simScenario, setSimScenario] = useState('normal');
  const [simDuration, setSimDuration] = useState(120);
  const [simSpeed,    setSimSpeed]    = useState(1.0);
  const [simRunning,  setSimRunning]  = useState({});
  const [simLoading,  setSimLoading]  = useState(false);
  const [simError,    setSimError]    = useState('');

  const { user }  = useAuth();
  const { t }     = useLang();
  const navigate  = useNavigate();

  const NAV = [
    t.admin.userManagement,
    t.admin.simulationManagement,
    t.admin.auditLogs,
    t.admin.dbBackup,
  ];

  useEffect(() => {
    axios.get(`${BASE}/admin/users`)
      .then(r => setUsers(r.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    api.getPatients()
      .then(r => {
        setPatients(r.data);
        if (r.data.length > 0) setSimPatient(r.data[0].patient_id);
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    api.getSimulationStatus()
      .then(r => setSimRunning(r.data))
      .catch(() => {});
  }, [activeNav]);

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
      setUsers(prev => prev.map(x =>
        x.user_id === u.user_id ? { ...x, is_active: !x.is_active } : x
      ));
    } catch (err) {
      alert(err.response?.data?.detail || 'İşlem başarısız.');
    }
  };

  const handleSimStart = async () => {
    if (!simPatient) return;
    setSimLoading(true);
    setSimError('');
    try {
      await api.startSimulation({
        patient_id: simPatient,
        scenario:   simScenario,
        duration:   simDuration,
        speed:      simSpeed,
      });
      setSimRunning(prev => ({ ...prev, [simPatient]: { status: 'running' } }));
    } catch (err) {
      setSimError(err.response?.data?.detail || 'Simülasyon başlatılamadı.');
    } finally {
      setSimLoading(false);
    }
  };

  const handleSimStop = async (patientId) => {
    setSimLoading(true);
    try {
      await api.stopSimulation(patientId);
      setSimRunning(prev => {
        const next = { ...prev };
        delete next[patientId];
        return next;
      });
    } catch (err) {
      setSimError(err.response?.data?.detail || 'Simülasyon durdurulamadı.');
    } finally {
      setSimLoading(false);
    }
  };

  const SCENARIOS = [
    { value: 'normal',  label: 'Normal' },
    { value: 'sepsis',  label: 'Sepsis' },
    { value: 'apnea',   label: 'Apnea' },
    { value: 'cardiac', label: 'Kardiyak' },
    { value: 'mixed',   label: 'Karışık' },
  ];

  return (
    <div>
      <Topbar title={t.admin.title} />
      <div style={{ display: 'flex', minHeight: 'calc(100vh - 56px)' }}>

        {/* Sidebar */}
        <div style={{ width: 220, background: 'var(--navy)', padding: '24px 0', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {NAV.map((item, i) => (
            <button key={item} onClick={() => setActiveNav(i)} style={{
              background: i === activeNav ? 'var(--teal)' : 'transparent',
              color: i === activeNav ? 'white' : 'rgba(255,255,255,0.7)',
              border: 'none', padding: '12px 20px', textAlign: 'left', fontSize: 14, cursor: 'pointer',
            }}>
              {item}
            </button>
          ))}
        </div>

        {/* İçerik */}
        <div className="page-content" style={{ flex: 1 }}>

          {/* Kullanıcı Yönetimi */}
          {activeNav === 0 && (
            <>
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
                        <input className="form-input" value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))} required />
                      </div>
                      <div className="form-group" style={{ margin: 0 }}>
                        <label className="form-label">{t.admin.password}</label>
                        <input className="form-input" type="password" value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} required />
                      </div>
                      <div className="form-group" style={{ margin: 0 }}>
                        <label className="form-label">{t.admin.displayName}</label>
                        <input className="form-input" value={form.display_name} onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))} required />
                      </div>
                      <div className="form-group" style={{ margin: 0 }}>
                        <label className="form-label">{t.admin.role}</label>
                        <select className="form-input" value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}>
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
                          <td>
                            <span className={u.is_active ? 'status-stable' : 'status-inactive'}>
                              {u.is_active ? t.admin.active : t.admin.inactive}
                            </span>
                          </td>
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
            </>
          )}

          {/* Simülasyon Yönetimi */}
          {activeNav === 1 && (
            <>
              <h2 style={{ color: 'var(--navy)', fontSize: 22, fontWeight: 700, marginBottom: 20 }}>
                {t.admin.simulationManagement}
              </h2>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
                {/* Simülasyon Başlat */}
                <div className="card">
                  <h3 style={{ color: 'var(--navy)', marginBottom: 16 }}>Yeni Simülasyon Başlat</h3>

                  <div className="form-group">
                    <label className="form-label">Hasta</label>
                    <select className="form-input" value={simPatient} onChange={e => setSimPatient(e.target.value)}>
                      {patients.length === 0 && <option value="">Hasta bulunamadı</option>}
                      {patients.map(p => (
                        <option key={p.patient_id} value={p.patient_id}>
                          {p.full_name} — GA:{p.gestational_age_weeks}w
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Senaryo</label>
                    <select className="form-input" value={simScenario} onChange={e => setSimScenario(e.target.value)}>
                      {SCENARIOS.map(s => (
                        <option key={s.value} value={s.value}>{s.label}</option>
                      ))}
                    </select>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    <div className="form-group">
                      <label className="form-label">Süre (dakika)</label>
                      <input className="form-input" type="number" min={1} max={60}
                        value={simDuration / 60}
                        onChange={e => setSimDuration(parseInt(e.target.value) * 60)} />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Hız (x)</label>
                      <select className="form-input" value={simSpeed} onChange={e => setSimSpeed(parseFloat(e.target.value))}>
                        <option value={1}>1x (gerçek zamanlı)</option>
                        <option value={2}>2x</option>
                        <option value={5}>5x</option>
                        <option value={10}>10x</option>
                      </select>
                    </div>
                  </div>

                  {simError && <p className="error-msg" style={{ marginBottom: 12 }}>{simError}</p>}

                  <button
                    className="btn btn-primary"
                    onClick={handleSimStart}
                    disabled={simLoading || !simPatient || simRunning[simPatient]?.status === 'running'}
                    style={{ width: '100%', justifyContent: 'center', padding: 12 }}
                  >
                    {simLoading ? 'Başlatılıyor...' : '▶ Simülasyonu Başlat'}
                  </button>
                </div>

                {/* Aktif Simülasyonlar */}
                <div className="card">
                  <h3 style={{ color: 'var(--navy)', marginBottom: 16 }}>Aktif Simülasyonlar</h3>
                  {Object.keys(simRunning).filter(k => simRunning[k]?.status === 'running').length === 0 ? (
                    <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>Aktif simülasyon yok.</p>
                  ) : (
                    Object.entries(simRunning)
                      .filter(([, v]) => v?.status === 'running')
                      .map(([pid]) => {
                        const p = patients.find(x => x.patient_id === pid);
                        return (
                          <div key={pid} style={{
                            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                            padding: '10px 14px', borderRadius: 8, background: 'var(--bg)',
                            marginBottom: 8, border: '1px solid var(--border)',
                          }}>
                            <div>
                              <p style={{ fontWeight: 500, fontSize: 13 }}>{p?.full_name || pid.slice(0, 8)}</p>
                              <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                                <span style={{ color: '#22c55e' }}>● </span>Çalışıyor
                              </p>
                            </div>
                            <button
                              className="btn btn-danger"
                              style={{ padding: '4px 14px', fontSize: 12 }}
                              onClick={() => handleSimStop(pid)}
                              disabled={simLoading}
                            >
                              ■ Durdur
                            </button>
                          </div>
                        );
                      })
                  )}
                </div>
              </div>
            </>
          )}

          {/* Stub sekmeler */}
          {activeNav > 1 && (
            <div className="card" style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 48 }}>
              <p style={{ fontSize: 16 }}>{NAV[activeNav]}</p>
              <p style={{ fontSize: 13, marginTop: 8 }}>Bu bölüm henüz geliştirme aşamasında.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}