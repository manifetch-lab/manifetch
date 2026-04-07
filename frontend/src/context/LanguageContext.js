import { createContext, useContext, useState } from 'react';
import tr from '../languages/tr';
import en from '../languages/en';

const LanguageContext = createContext(null);

export function LanguageProvider({ children }) {
  const [lang, setLang] = useState(localStorage.getItem('lang') || 'tr');

  const toggle = () => {
    const next = lang === 'tr' ? 'en' : 'tr';
    setLang(next);
    localStorage.setItem('lang', next);
  };

  const t = lang === 'tr' ? tr : en;

  return (
    <LanguageContext.Provider value={{ lang, toggle, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLang() {
  return useContext(LanguageContext);
}