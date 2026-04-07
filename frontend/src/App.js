import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { LanguageProvider } from './context/LanguageContext';
import PrivateRoute from './components/PrivateRoute';

import LoginPage from './pages/LoginPage';
import PatientListPage from './pages/PatientListPage';
import PatientDetailPage from './pages/PatientDetailPage';
import AdminPage from './pages/AdminPage';

function HomeRedirect() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === 'ADMINISTRATOR') return <Navigate to="/admin" replace />;
  return <Navigate to="/patients" replace />;
}

function App() {
  return (
    <LanguageProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/patients" element={
              <PrivateRoute><PatientListPage /></PrivateRoute>
            } />
            <Route path="/patients/:patientId" element={
              <PrivateRoute><PatientDetailPage /></PrivateRoute>
            } />
            <Route path="/admin" element={
              <PrivateRoute roles={['ADMINISTRATOR']}><AdminPage /></PrivateRoute>
            } />
            <Route path="/" element={<HomeRedirect />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </LanguageProvider>
  );
}

export default App;