import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import Topbar from '../components/Topbar';
import { api } from '../api/client';

export default function PatientListPage() {
  const [patients, setPatients] = useState([]);
  const [search,   setSearch]   = useState('');
  const [loading,  setLoading]  = useState(true);
  const [showAdd,  setShowAdd]  = useState(false);
  const [form,     setForm]     = useState({ full_name: '', gestational_age_weeks: '', postnatal_age_days: '' });
  const [formErr,  setFormErr]  = useState('');
  const { user }   = useAuth();
  const navigate   = useNavigate();
  const canAdd     = ['DOCTOR', 'NURSE'].includes(user?.role);

  // Admin hasta listesine giremez
  useEffect(() => {
    if (user?.role === 'ADMINISTRATOR') {
      navigate('/admin', { replace: true });
      return;
    }
    api.getPatients()
      .then(r => setPatients(r.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [user, navigate]);

  const filtered = patients.filter(p =>
    p.full_name.toLowerCase().includes(search.toLowerCase())
  );

  const handleAdd = async (e) => {
    e.preventDefault();
    setFormErr('');
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
      setFormErr(err.response?.data?.detail || 'Hasta eklenemedi.');
    }
  };

  return (
    <div>
      <Topbar title="Patient Dashboard" />
      <div className="page-content">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <input
            className="form-input"
            placeholder="🔍  Search patients..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ width: 340 }}
          />
          {canAdd && (
            <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
              + Add Patient
            </button>
          )}
        </div>

        {showAdd && (
          <div className="card" style={{ marginBottom: 20 }}>
            <h3 style={{ marginBottom: 16, color: 'var(--navy)' }}>New Patient</h3>
            <form onSubmit={handleAdd}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
                <div className="form-group" style={{ margin: 0 }}>
                  <label className="form-label">Full Name</label>
                  <input className="form-input" value={form.full_name}
                    onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} required />
                </div>
                <div className="form-group" style={{ margin: 0 }}>
                  <label className="form-label">Gestational Age (weeks)</label>
                  <input className="form-input" type="number" min={22} max={42}
                    value={form.gestational_age_weeks}
                    onChange={e => setForm(f => ({ ...f, gestational_age_weeks: e.target.value }))} required />
                </div>
                <div className="form-group" style={{ margin: 0 }}>
                  <label className="form-label">Postnatal Age (days)</label>
                  <input className="form-input" type="number" min={0} max={365}
                    value={form.postnatal_age_days}
                    onChange={e => setForm(f => ({ ...f, postnatal_age_days: e.target.value }))} required />
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

        <div className="table-wrapper">
          {loading ? (
            <div className="loading"><div className="spinner" />Loading patients...</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Name</th>
                  <th>Age (days)</th>
                  <th>Status</th>
                  <th>Last Updated</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 32 }}>No patients found.</td></tr>
                ) : filtered.map((p, i) => (
                  <tr key={p.patient_id}>
                    <td style={{ fontFamily: 'DM Mono, monospace', fontSize: 12 }}>{String(i + 1).padStart(3, '0')}</td>
                    <td style={{ fontWeight: 500 }}>{p.full_name}</td>
                    <td>{p.postnatal_age_days}</td>
                    <td><span className="status-stable">Stable</span></td>
                    <td style={{ color: 'var(--text-muted)' }}>
                      {new Date(p.admission_date).toLocaleDateString()}
                    </td>
                    <td>
                      <button className="btn btn-outline" style={{ padding: '4px 14px', fontSize: 13 }}
                        onClick={() => navigate(`/patients/${p.patient_id}`)}>
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}