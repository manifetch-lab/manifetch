import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const AuthContext = createContext(null);

const API = process.env.REACT_APP_API_URL || 'http://127.0.0.1:8000';

// DÜZELTME: localStorage yerine sessionStorage — XSS riski azaltıldı
// NFR-1.10: "sensitive information in client-side storage" → sessionStorage
// Tab kapatılınca oturum otomatik sona erer
const storage = {
  get:    (key)        => sessionStorage.getItem(key),
  set:    (key, value) => sessionStorage.setItem(key, value),
  remove: (key)        => sessionStorage.removeItem(key),
  clear:  ()           => sessionStorage.clear(),
};

export function AuthProvider({ children }) {
  const [user,    setUser]    = useState(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    delete axios.defaults.headers.common['Authorization'];
    storage.clear();
    setUser(null);
  }, []);

  // Uygulama başlangıcında mevcut oturumu yükle
  useEffect(() => {
    const token        = storage.get('token');
    const role         = storage.get('role');
    const display_name = storage.get('display_name');
    const user_id      = storage.get('user_id');
    const refreshToken = storage.get('refresh_token');

    if (token) {
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
      setUser({ token, role, display_name, user_id, refreshToken });
    }
    setLoading(false);
  }, []);

  // DÜZELTME: 401 interceptor — token expiry otomatik handle edilir
  useEffect(() => {
    let isRefreshing = false;
    let failedQueue  = [];

    const processQueue = (error, token = null) => {
      failedQueue.forEach(prom => {
        if (error) prom.reject(error);
        else       prom.resolve(token);
      });
      failedQueue = [];
    };

    const interceptor = axios.interceptors.response.use(
      response => response,
      async error => {
        const originalRequest = error.config;

        if (error.response?.status === 401 && !originalRequest._retry) {
          const refreshToken = storage.get('refresh_token');

          // Refresh token yoksa direkt logout
          if (!refreshToken) {
            logout();
            return Promise.reject(error);
          }

          if (isRefreshing) {
            // Başka bir refresh devam ediyorsa kuyruğa ekle
            return new Promise((resolve, reject) => {
              failedQueue.push({ resolve, reject });
            }).then(token => {
              originalRequest.headers['Authorization'] = `Bearer ${token}`;
              return axios(originalRequest);
            });
          }

          originalRequest._retry = true;
          isRefreshing           = true;

          try {
            const res = await axios.post(`${API}/auth/refresh`, {
              refresh_token: refreshToken,
            });
            const { access_token, refresh_token: newRefresh } = res.data;

            storage.set('token',         access_token);
            storage.set('refresh_token', newRefresh);
            axios.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;

            processQueue(null, access_token);
            originalRequest.headers['Authorization'] = `Bearer ${access_token}`;
            return axios(originalRequest);
          } catch (refreshError) {
            processQueue(refreshError, null);
            logout();
            return Promise.reject(refreshError);
          } finally {
            isRefreshing = false;
          }
        }

        return Promise.reject(error);
      }
    );

    return () => axios.interceptors.response.eject(interceptor);
  }, [logout]);

  const login = async (username, password) => {
    const form = new URLSearchParams();
    form.append('username', username);
    form.append('password', password);

    const res = await axios.post(`${API}/auth/login`, form);
    const { access_token, refresh_token, role, display_name, user_id } = res.data;

    axios.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;

    // DÜZELTME: sessionStorage kullan
    storage.set('token',         access_token);
    storage.set('refresh_token', refresh_token);
    storage.set('role',          role);
    storage.set('display_name',  display_name);
    storage.set('user_id',       user_id);

    setUser({ token: access_token, refreshToken: refresh_token, role, display_name, user_id });
    return role;
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, loading }}>
      {!loading && children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}