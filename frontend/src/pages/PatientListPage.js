import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useLang } from '../context/LanguageContext';
import Topbar from '../components/Topbar';
import { api } from '../api/client';

export default function PatientListPage() {
  const [patients,    setPatients]    = useState([]);
  const [search,      setSearch]      = useState('');
  const [sortBy,      setSortBy]      = useState('date');
  const [sortDir,     setSortDir]     = useState('desc');
  const [loading,     setLoading]     = useState(true);
  const [showAdd,     setShowAdd]     = useState(false);
  const [editPatient, setEditPatient] = useState(null);
  const [editForm,    setEditForm]    = useState({ full_name: '', postnatal_age_days: '', gestational_age_weeks: '' });
  const [editErr,     setEditErr]     = useState('');
  const [form,        setForm]        = useState({ full_name: '', gestational_age_weeks: '', postnatal_age_days: '' });
  const [formErr,     setFormErr]     = useState('');
  const { user }  = useAuth();
  const { t }     = useLang();
  const navigate  = useNavigate();
  const canAdd    = ['DOCTOR', 'NURSE'].includes(user?.role);

  useEffect(() => {
    if (user?.role === 'ADMINISTRATOR') { navigate('/admin', { replace: true }); return; }
    api.getPatients()
      .then(r => setPatients(r.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [user, navigate]);

  const handleSort = (col) => {
    if (sortBy === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortBy(col); setSortDir('asc'); }
  };
  const sortIcon = (col) => sortBy !== col ? ' ↕' : sortDir === 'asc' ? ' ↑' : ' ↓';

  const filtered = patients
    .filter(p => p.full_name.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      let valA, valB;
      if (sortBy === 'name')     { valA = a.full_name; valB = b.full_name; }
      else if (sortBy === 'age') { valA = a.postnatal_age_days; valB = b.postnatal_age_days; }
      else                       { valA = new Date(a.admission_date); valB = new Date(b.admission_date); }
      if (valA < valB) return sortDir === 'asc' ? -1 : 1;
      if (valA > valB) return sortDir === 'asc' ?  1 : -1;
      return 0;
    });

  const handleAdd = async (e) => {
    e.preventDefault(); setFormErr('');
    try {
      const res = await api.createPatient({
        full_name:             form.full_name,
        gestational_age_weeks: parseInt(form.gestational_age_weeks),
        postnatal_age_days:    parseInt(form.postnatal_age_days),
      });
      setPatients(prev => [res.data, ...prev]);
      setShowAdd(false);
      setForm({ full_name: '', gestational_age_weeks: '', postnatal_age_days: '' });
    } catch (err) {
      setFormErr(err.response?.data?.detail || t.patientList.errorAdd);
    }
  };

  const openEdit = (p) => {
    setEditPatient(p);
    setEditForm({
      full_name:             p.full_name,
      postnatal_age_days:    String(p.postnatal_age_days),
      gestational_age_weeks: String(p.gestational_age_weeks),
    });
    setEditErr('');
  };

  const handleEdit = async (e) => {
    e.preventDefault(); setEditErr('');
    try {
      const res = await api.updatePatient(editPatient.patient_id, {
        full_name:             editForm.full_name,
        postnatal_age_days:    parseInt(editForm.postnatal_age_days),
        gestational_age_weeks: parseInt(editForm.gestational_age_weeks),
      });
      setPatients(prev => prev.map(p =>
        p.patient_id === editPatient.patient_id ? { ...p, ...res.data } : p
      ));
      setEditPatient(null);
    } catch (err) {
      setEditErr(err.response?.data?.detail || 'Güncelleme başarısız.');
    }
  };

  return (
    <div>
      <Topbar title={t.patientList.title} />
      <div className="page-content">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, gap: 12 }}>
          <input className="form-input" placeholder={t.patientList.search}
            value={search} onChange={e => setSearch(e.target.value)} style={{ width: 300 }} />
          <div style={{ marginLeft: 'auto' }}>
            {canAdd && (
              <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
                {t.patientList.addPatient}
              </button>
            )}
          </div>
        </div>

        {/* Yeni hasta formu */}
        {showAdd && (
          <div className="card" style={{ marginBottom: 20 }}>
            <h3 style={{ marginBottom: 16, color: 'var(--navy)' }}>{t.patientList.newPatient}</h3>
            <form onSubmit={handleAdd}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
                <div className="form-group" style={{ margin: 0 }}>
                  <label className="form-label">{t.patientList.fullName}</label>
                  <input className="form-input" value={form.full_name}
                    onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} required />
                </div>
                <div className="form-group" style={{ margin: 0 }}>
                  <label className="form-label">{t.patientList.gestationalAge}</label>
                  <input className="form-input" type="number" min={22} max={42}
                    value={form.gestational_age_weeks}
                    onChange={e => setForm(f => ({ ...f, gestational_age_weeks: e.target.value }))} required />
                </div>
                <div className="form-group" style={{ margin: 0 }}>
                  <label className="form-label">{t.patientList.postnatalAge}</label>
                  <input className="form-input" type="number" min={0} max={365}
                    value={form.postnatal_age_days}
                    onChange={e => setForm(f => ({ ...f, postnatal_age_days: e.target.value }))} required />
                </div>
              </div>
              {formErr && <p className="error-msg" style={{ marginTop: 8 }}>{formErr}</p>}
              <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
                <button className="btn btn-primary" type="submit">{t.patientList.save}</button>
                <button className="btn btn-outline" type="button" onClick={() => setShowAdd(false)}>{t.patientList.cancel}</button>
              </div>
            </form>
          </div>
        )}

        {/* Düzenleme modal */}
        {editPatient && (
          <div style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999,
          }}>
            <div className="card" style={{ width: 440, padding: 28 }}>
              <h3 style={{ marginBottom: 16, color: 'var(--navy)' }}>Hasta Güncelle</h3>
              <form onSubmit={handleEdit}>
                <div className="form-group">
                  <label className="form-label">{t.patientList.fullName}</label>
                  <input className="form-input" value={editForm.full_name}
                    onChange={e => setEditForm(f => ({ ...f, full_name: e.target.value }))} required />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                  <div className="form-group" style={{ margin: 0 }}>
                    <label className="form-label">{t.patientList.gestationalAge}</label>
                    <input className="form-input" type="number" min={22} max={42}
                      value={editForm.gestational_age_weeks}
                      onChange={e => setEditForm(f => ({ ...f, gestational_age_weeks: e.target.value }))} required />
                  </div>
                  <div className="form-group" style={{ margin: 0 }}>
                    <label className="form-label">{t.patientList.postnatalAge}</label>
                    <input className="form-input" type="number" min={0} max={365}
                      value={editForm.postnatal_age_days}
                      onChange={e => setEditForm(f => ({ ...f, postnatal_age_days: e.target.value }))} required />
                  </div>
                </div>
                <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8, marginBottom: 16 }}>
                  Not: Gestasyonel yaş değiştirildiğinde threshold kuralları otomatik güncellenir.
                </p>
                {editErr && <p className="error-msg" style={{ marginBottom: 8 }}>{editErr}</p>}
                <div style={{ display: 'flex', gap: 10 }}>
                  <button className="btn btn-primary" type="submit">{t.patientList.save}</button>
                  <button className="btn btn-outline" type="button" onClick={() => setEditPatient(null)}>{t.patientList.cancel}</button>
                </div>
              </form>
            </div>
          </div>
        )}

        <div className="table-wrapper">
          {loading ? (
            <div className="loading"><div className="spinner" />{t.patientList.loading}</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>{t.patientList.id}</th>
                  <th style={{ cursor: 'pointer', userSelect: 'none' }} onClick={() => handleSort('name')}>
                    {t.patientList.name}{sortIcon('name')}
                  </th>
                  <th style={{ cursor: 'pointer', userSelect: 'none' }} onClick={() => handleSort('age')}>
                    {t.patientList.ageDays}{sortIcon('age')}
                  </th>
                  <th>{t.patientList.status}</th>
                  <th style={{ cursor: 'pointer', userSelect: 'none' }} onClick={() => handleSort('date')}>
                    {t.patientList.lastUpdated}{sortIcon('date')}
                  </th>
                  <th>{t.patientList.actions}</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 32 }}>{t.patientList.noPatients}</td></tr>
                ) : filtered.map((p, i) => (
                  <tr key={p.patient_id}>
                    <td style={{ fontFamily: 'DM Mono, monospace', fontSize: 12 }}>{String(i + 1).padStart(3, '0')}</td>
                    <td style={{ fontWeight: 500 }}>{p.full_name}</td>
                    <td>{p.postnatal_age_days}</td>
                    <td>
                      <span className={
                        p.alert_status === 'CRITICAL' ? 'status-critical' :
                        p.alert_status === 'MONITORING' ? 'status-monitoring' :
                        'status-stable'
                      }>
                        {p.alert_status === 'CRITICAL' ? t.patientList.critical :
                         p.alert_status === 'MONITORING' ? t.patientList.monitoring :
                         t.patientList.stable}
                      </span>
                    </td>
                    <td style={{ color: 'var(--text-muted)' }}>{new Date(p.admission_date).toLocaleDateString()}</td>
                    <td>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button
                          className="btn btn-outline"
                          style={{ padding: '4px 14px', fontSize: 13 }}
                          onClick={() => navigate(`/patients/${p.patient_id}`)}>
                          {t.patientList.view}
                        </button>
                        {canAdd && p.is_active && (
                          <button
                            onClick={() => openEdit(p)}
                            style={{
                              padding: '4px 14px', fontSize: 13,
                              background: 'transparent',
                              border: '1.5px solid var(--border)',
                              borderRadius: 6, cursor: 'pointer',
                              color: 'var(--text-muted)',
                            }}>
                            ✏️
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {!loading && (
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 10, textAlign: 'right' }}>
            {filtered.length} / {patients.length} hasta
          </p>
        )}
      </div>
    </div>
  );
}