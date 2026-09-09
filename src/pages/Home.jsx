import { useNavigate } from 'react-router-dom';
import { Brain, MapPin, Bell } from 'lucide-react';
import { useApp } from '../context/AppContext';

export default function Home() {
  const { t } = useApp();
  const navigate = useNavigate();

  const features = [
    { icon: Brain, titleKey: 'riskAssessment', descKey: 'riskAssessmentDesc' },
    { icon: MapPin, titleKey: 'hospitalNav', descKey: 'hospitalNavDesc' },
    { icon: Bell, titleKey: 'smartNotify', descKey: 'smartNotifyDesc' },
  ];

  return (
    <div className="home-page page-transition">
      {/* ── Hero ── */}
      <section className="hero">
        <div className="hero-content">
          <h1 className="hero-title">{t('heroTitle')}</h1>
          <p className="hero-subtext">{t('heroSubtext')}</p>
          <button className="hero-cta" onClick={() => navigate('/triage')}>
            {t('startTriage')}
          </button>
        </div>

        {/* ECG Heartbeat Line */}
        <div className="ecg-wrapper">
          <svg className="ecg-svg" viewBox="0 0 1200 100" preserveAspectRatio="none">
            <polyline
              className="ecg-line"
              fill="none"
              stroke="var(--accent)"
              strokeWidth="2"
              points="
                0,50 100,50 120,50 140,20 160,80 180,10 200,90 220,50
                240,50 340,50 360,50 380,20 400,80 420,10 440,90 460,50
                480,50 580,50 600,50 620,20 640,80 660,10 680,90 700,50
                720,50 820,50 840,50 860,20 880,80 900,10 920,90 940,50
                960,50 1060,50 1080,50 1100,20 1120,80 1140,10 1160,90 1200,50
              "
            />
          </svg>
        </div>
      </section>

      {/* ── Feature Cards ── */}
      <section className="features">
        {features.map(({ icon: Icon, titleKey, descKey }) => (
          <div className="feature-card glass" key={titleKey}>
            <div className="feature-icon">
              <Icon size={28} />
            </div>
            <h3>{t(titleKey)}</h3>
            <p>{t(descKey)}</p>
          </div>
        ))}
      </section>

      {/* ── Stats Bar ── */}
      <section className="stats-bar glass">
        <div className="stat">
          <span className="stat-value">12,000+</span>
          <span className="stat-label">{t('statPatients')}</span>
        </div>
        <div className="stat-divider" />
        <div className="stat">
          <span className="stat-value">98%</span>
          <span className="stat-label">{t('statAccuracy')}</span>
        </div>
        <div className="stat-divider" />
        <div className="stat">
          <span className="stat-value">3-Min</span>
          <span className="stat-label">{t('statAvgTriage')}</span>
        </div>
      </section>
    </div>
  );
}
