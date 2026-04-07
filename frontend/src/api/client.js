import axios from 'axios';

const BASE = 'http://127.0.0.1:8000';

export const api = {
  login: (username, password) => {
    const form = new URLSearchParams();
    form.append('username', username);
    form.append('password', password);
    return axios.post(`${BASE}/auth/login`, form);
  },

  getPatients:      ()          => axios.get(`${BASE}/dashboard/patients`),
  getPatient:       (id)        => axios.get(`${BASE}/dashboard/patients/${id}`),
  createPatient:    (data)      => axios.post(`${BASE}/patients`, data),
  updatePatient:    (id, data)  => axios.put(`${BASE}/patients/${id}`, data),
  archivePatient:   (id)        => axios.patch(`${BASE}/patients/${id}/archive`),

  getAlerts:        (id, status) => axios.get(`${BASE}/dashboard/patients/${id}/alerts`, { params: { status } }),
  acknowledgeAlert: (alertId)    => axios.patch(`${BASE}/dashboard/alerts/${alertId}/acknowledge`),
  resolveAlert:     (alertId)    => axios.patch(`${BASE}/dashboard/alerts/${alertId}/resolve`),

  getVitals:        (id, type, limit) => axios.get(`${BASE}/dashboard/patients/${id}/vitals`, { params: { signal_type: type, limit } }),
  getTrends:        (id, type, hours) => axios.get(`${BASE}/dashboard/patients/${id}/trends`, { params: { signal_type: type, hours } }),

  getAIResults:     (id)        => axios.get(`${BASE}/dashboard/patients/${id}/ai`),

  getReport:        (id, days, lang) => axios.get(`${BASE}/dashboard/patients/${id}/report`, {
    params: { days, lang },
    responseType: 'blob',
  }),

  startStream:      (id)        => axios.post(`${BASE}/patients/${id}/streams`),
  stopStream:       (streamId)  => axios.patch(`${BASE}/patients/streams/${streamId}/stop`),
};