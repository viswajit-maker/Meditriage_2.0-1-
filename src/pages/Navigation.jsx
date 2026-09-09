import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MapPin, Star, Building2, CheckCircle } from 'lucide-react';
import { useApp } from '../context/AppContext';

const HOSPITALS = [
  { id: 1, name: "Govt. Rajiv Gandhi Hospital", dist: "1.2 km", type: "government", stars: 4, specialties: "General, Emergency" },
  { id: 2, name: "Apollo Clinic Tambaram", dist: "2.8 km", type: "private", stars: 5, specialties: "Multi-Specialty" },
  { id: 3, name: "Primary Health Centre Chrompet", dist: "0.9 km", type: "government", stars: 3, specialties: "General" },
  { id: 4, name: "MIOT International", dist: "4.1 km", type: "private", stars: 4, specialties: "Cardiology, Ortho" },
  { id: 5, name: "SRM Medical College Hospital", dist: "3.5 km", type: "private", stars: 4, specialties: "Teaching Hospital" },
];

export default function Navigation() {
  const { t, setSelectedHospital } = useApp();
  const navigate = useNavigate();
  const [selected, setSelected] = useState(null);

  const handleSelect = (h) => {
    setSelected(h);
    setSelectedHospital(h);
  };

  return (
    <div className="nav-page page-transition">
      {/* Map Embed */}
      <div className="map-container glass">
        <iframe
          title="Hospitals near Chennai"
          src="https://maps.google.com/maps?q=hospitals+near+chennai&output=embed"
          width="100%"
          height="350"
          style={{ border: 0, borderRadius: '14px', display: 'block' }}
          allowFullScreen
          loading="lazy"
          referrerPolicy="no-referrer-when-downgrade"
        />
      </div>

      {/* Selected Banner */}
      {selected && (
        <div className="selected-banner">
          <CheckCircle size={18} />
          <span>{t('hospitalSelected')}</span>
          <button className="banner-btn" onClick={() => navigate('/booking')}>
            {t('booking')} →
          </button>
        </div>
      )}

      <h2 className="nav-section-title">{t('nearbyHospitals')}</h2>

      {/* Hospital Cards Grid */}
      <div className="hospital-grid">
        {HOSPITALS.map((h) => (
          <div
            className={`hospital-card glass${selected?.id === h.id ? ' card-selected' : ''}`}
            key={h.id}
          >
            <div className="hospital-card-top">
              <h3 className="hospital-name">{h.name}</h3>
              <span className="dist-badge">
                <MapPin size={12} />
                {h.dist}
              </span>
            </div>

            <div className="hospital-meta">
              <span className={`type-badge ${h.type}`}>
                <Building2 size={12} />
                {t(h.type)}
              </span>
              <span className="stars">
                {Array.from({ length: 5 }, (_, i) => (
                  <Star
                    key={i}
                    size={14}
                    fill={i < h.stars ? '#ffa502' : 'transparent'}
                    stroke={i < h.stars ? '#ffa502' : 'var(--muted)'}
                  />
                ))}
              </span>
            </div>

            <p className="hospital-spec">
              <span className="spec-label">{t('specialties')}:</span> {h.specialties}
            </p>

            <button
              className={`select-hospital-btn${selected?.id === h.id ? ' selected' : ''}`}
              onClick={() => handleSelect(h)}
            >
              {selected?.id === h.id ? '✓ Selected' : t('selectHospital')}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
