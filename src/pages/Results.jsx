import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  CalendarCheck,
  CheckCircle,
  Download,
  MapPin,
  ShieldAlert,
  Stethoscope,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { useToast } from '../context/ToastContext';

const RISK_CONFIG = {
  High: { color: 'var(--high)', pct: 95 },
  Medium: { color: 'var(--medium)', pct: 55 },
  Low: { color: 'var(--low)', pct: 20 },
};

export default function Results() {
  const { t, patientData, riskResult } = useApp();
  const { showToast } = useToast();
  const navigate = useNavigate();
  const [gaugeAnim, setGaugeAnim] = useState(0);

  useEffect(() => {
    if (!patientData) navigate('/triage');
  }, [patientData, navigate]);

  useEffect(() => {
    if (!riskResult) return undefined;
    const target = RISK_CONFIG[riskResult.riskLevel]?.pct || RISK_CONFIG.Medium.pct;
    const timer = setTimeout(() => setGaugeAnim(target), 100);
    return () => clearTimeout(timer);
  }, [riskResult]);

  if (!patientData) return null;

  if (!riskResult) {
    return (
      <div className="results-page page-transition centered-view">
        <div className="error-card glass">
          <AlertTriangle size={48} color="var(--high)" />
          <h2>No completed assessment is available yet.</h2>
          <button className="submit-btn" onClick={() => navigate('/triage')}>Return to intake form</button>
        </div>
      </div>
    );
  }

  const risk = riskResult.riskLevel || 'Medium';
  const cfg = RISK_CONFIG[risk] || RISK_CONFIG.Medium;
  const radius = 80;
  const circumference = Math.PI * radius;
  const offset = circumference - (gaugeAnim / 100) * circumference;
  const precautions = riskResult.precautions || [];

  if (riskResult.emergencyOverride) {
    return (
      <div className="results-page page-transition">
        <h2 className="results-title">Emergency Detected</h2>
        <p className="assessment-subtitle">Immediate attention required for {patientData.name}</p>

        <div className="emergency-banner" style={{ padding: '24px', margin: '20px 0', fontSize: '1.2rem', textAlign: 'center' }}>
          <ShieldAlert size={48} style={{ marginBottom: '16px' }} />
          <h2>Emergency symptoms detected</h2>
          <p style={{ marginTop: '12px' }}>{riskResult.clinicalSummary}</p>
          <p style={{ marginTop: '12px', fontWeight: 'bold' }}>{riskResult.recommendation}</p>
        </div>

        <p className="medical-disclaimer" style={{ fontSize: '1.1rem', fontWeight: 'bold', color: 'var(--text)' }}>
          {riskResult.disclaimer || "This tool provides a preliminary assessment, not a medical diagnosis. For severe, sudden, or worsening symptoms, seek urgent medical care."}
        </p>

        <div className="results-actions" style={{ marginTop: '30px' }}>
          <button className="cta-btn primary" onClick={() => navigate('/navigation')}><MapPin size={18} />{t('findHospitals')}</button>
        </div>
      </div>
    );
  }

  return (
    <div className="results-page page-transition">
      <h2 className="results-title">
        {riskResult.predictedDisease ? `${riskResult.predictedDisease} (${riskResult.confidenceScore}%)` : 'Medical Assessment'}
      </h2>
      <p className="assessment-subtitle">Preliminary symptom assessment for {patientData.name}</p>

      <div className="risk-badge-wrapper">
        <div className="risk-badge" style={{ '--risk-color': cfg.color }}>
          <span className="risk-badge-text">{risk} Risk</span>
        </div>
      </div>

      <div className="gauge-wrapper">
        <svg className="gauge-svg" viewBox="0 0 200 110" aria-label={`${risk} risk assessment`}>
          <path className="gauge-bg" d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="rgba(100,116,139,0.15)" strokeWidth="12" strokeLinecap="round" />
          <path className="gauge-fill" d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke={cfg.color} strokeWidth="12" strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset} style={{ transition: 'stroke-dashoffset 1.2s ease-out', filter: `drop-shadow(0 0 8px ${cfg.color})` }} />
          <text x="100" y="90" textAnchor="middle" fill={cfg.color} fontSize="28" fontWeight="800">{gaugeAnim}%</text>
        </svg>
      </div>

      {riskResult.matchedSymptoms?.length > 0 && (
        <div className="symptoms-pills" aria-label="Matched symptoms">
          {riskResult.matchedSymptoms.map((symptom) => <span key={symptom} className="teal-pill">{symptom}</span>)}
        </div>
      )}

      <div className="condition-card glass">
        <h3>Assessment summary</h3>
        <p>{riskResult.clinicalSummary}</p>

        <div className="recommendation-line">
          <CheckCircle size={20} className="icon-green" />
          <span>{riskResult.recommendation}</span>
        </div>
        <div className="recommendation-line">
          <Stethoscope size={20} className="icon-teal" />
          <span>Recommended specialist: {riskResult.specialistReferral}</span>
        </div>
      </div>

      {riskResult.differential && riskResult.differential.length > 0 && (
        <div className="condition-card glass differential-card">
          <h3>Other possible conditions</h3>
          <ul style={{ paddingLeft: '20px', lineHeight: '1.6' }}>
            {riskResult.differential.map((diff) => (
              <li key={diff.disease}>{diff.disease} ({diff.confidence}%)</li>
            ))}
          </ul>
        </div>
      )}

      <div className="condition-card glass precautions-card">
        <h3>Recommended precautions</h3>
        {precautions.length > 0 ? (
          <ul className="precautions-list">
            {precautions.map((precaution) => <li key={precaution}>{precaution}</li>)}
          </ul>
        ) : (
          <p>No specific precautions on file — please consult a doctor</p>
        )}
      </div>

      <p className="medical-disclaimer" style={{ fontSize: '1rem', fontWeight: 'bold', color: 'var(--text)' }}>
        {riskResult.disclaimer || "This tool provides a preliminary assessment, not a medical diagnosis. For severe, sudden, or worsening symptoms, seek urgent medical care."}
      </p>

      <div className="results-actions">
        <button className="cta-btn primary" onClick={() => navigate('/navigation')}><MapPin size={18} />{t('findHospitals')}</button>
        <button className="cta-btn secondary" onClick={() => navigate('/booking')}><CalendarCheck size={18} />{t('bookAppointment')}</button>
      </div>
      <button className="export-btn" onClick={() => showToast(t('reportExported'))} aria-label="Export report"><Download size={16} />{t('exportReport')}</button>
    </div>
  );
}
