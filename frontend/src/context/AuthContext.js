import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('token');
    const role  = localStorage.getItem('role');
    const name  = localStorage.getItem('display_name');
    const uid   = localStorage.getItem('user_id');
    if (token) {
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
      setUser({ token, role, display_name: name, user_id: uid });
    }
    setLoading(false);
  }, []);

  const login = async (username, password) => {
    const form = new URLSearchParams();
    form.append('username', username);
    form.append('password', password);
    const res = await axios.post('http://127.0.0.1:8000/auth/login', form);
    const { access_token, role, display_name, user_id } = res.data;
    axios.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
    localStorage.setItem('token',        access_token);
    localStorage.setItem('role',         role);
    localStorage.setItem('display_name', display_name);
    localStorage.setItem('user_id',      user_id);
    setUser({ token: access_token, role, display_name, user_id });
    return role;
  };

  const logout = () => {
    delete axios.defaults.headers.common['Authorization'];
    localStorage.clear();
    setUser(null);
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