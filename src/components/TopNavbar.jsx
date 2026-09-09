import { useApp } from '../context/AppContext';

const langs = [
  { code: 'en', label: 'EN' },
  { code: 'hi', label: 'हि' },
  { code: 'ta', label: 'த' },
];

export default function TopNavbar() {
  const { language, setLanguage } = useApp();

  return (
    <header className="topbar glass">
      <div className="topbar-brand">
        <h1>MediTriage AI</h1>
        <span className="pulse-dot" />
      </div>
      <div className="lang-switcher">
        {langs.map(({ code, label }) => (
          <button
            key={code}
            className={`lang-btn${language === code ? ' active' : ''}`}
            onClick={() => setLanguage(code)}
          >
            {label}
          </button>
        ))}
      </div>
    </header>
  );
}
