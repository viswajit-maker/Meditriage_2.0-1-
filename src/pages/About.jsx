import { useApp } from '../context/AppContext';

export default function About() {
  const { t } = useApp();

  return (
    <div className="about-page page-transition">
      <div className="about-content glass">
        <h1>{t('aboutTitle') || 'MediTriage AI'}</h1>
        <p>{t('aboutSubtitle') || 'AI-Powered Smart Triage & Healthcare Navigation System'}</p>

        <h2>{t('techStack') || 'Tech Stack'}</h2>
        <ul>
          <li><strong>Frontend:</strong> React 18, Vite, React Router</li>
          <li><strong>Styling:</strong> Vanilla CSS with CSS Variables, Glassmorphism</li>
          <li><strong>Icons:</strong> lucide-react</li>
          <li><strong>State Management:</strong> React Context API</li>
          <li><strong>PWA:</strong> Manifest & Service Worker caching</li>
        </ul>

        <h2>{t('featuresList') || 'Key Features'}</h2>
        <ul>
          <li>Multilingual Support (EN, HI, TA)</li>
          <li>Real-time Emergency Keyword Detection</li>
          <li>Visual Risk Assessment (SVGs, Badges)</li>
          <li>Hospital Navigation & Booking Flow</li>
          <li>Doctor Dashboard with Triage Queue</li>
          <li>Automated SMS Trigger Panel</li>
          <li>Export functionalities (CSV, PDF mock)</li>
        </ul>

        <h2>{t('futureScope') || 'Future Scope'}</h2>
        <ul>
          <li><strong>Offline Kiosks:</strong> Edge-AI deployment in rural healthcare booths.</li>
          <li><strong>IoT Integration:</strong> Direct connection to vitals hardware (SpO2, BP).</li>
          <li><strong>API Integration:</strong> Connect to real hospital beds availability API.</li>
          <li><strong>Telemedicine:</strong> Video consultation directly from the app.</li>
        </ul>
      </div>
    </div>
  );
}
