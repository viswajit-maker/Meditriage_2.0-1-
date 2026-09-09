import { useState, useEffect } from 'react';
import { Download, Eye, X } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { useToast } from '../context/ToastContext';
import SmsPanel from '../components/SmsPanel';

const PATIENTS = [
  { id: 1, name: "Priya Sharma", age: 34, gender: "Female", symptoms: "Chest pain, shortness of breath", risk: "High", time: "10:32 AM" },
  { id: 2, name: "Ravi Kumar", age: 52, gender: "Male", symptoms: "Fever, body ache, fatigue", risk: "Medium", time: "10:45 AM" },
  { id: 3, name: "Anitha Devi", age: 28, gender: "Female", symptoms: "Mild cough, sore throat", risk: "Low", time: "11:00 AM" },
  { id: 4, name: "Mohammed Aslam", age: 67, gender: "Male", symptoms: "Unconscious, severe bleeding", risk: "High", time: "11:10 AM" },
  { id: 5, name: "Kavitha R", age: 41, gender: "Female", symptoms: "Headache, vomiting, dizziness", risk: "Medium", time: "11:22 AM" },
  { id: 6, name: "Suresh Babu", age: 19, gender: "Male", symptoms: "Cold, runny nose", risk: "Low", time: "11:35 AM" },
];

const PRIORITY = { High: 3, Medium: 2, Low: 1 };
const RISK_COLORS = { High: 'var(--high)', Medium: 'var(--medium)', Low: 'var(--low)' };

const sorted = [...PATIENTS].sort((a, b) => PRIORITY[b.risk] - PRIORITY[a.risk]);

export default function Dashboard() {
  const { t } = useApp();
  const { showToast } = useToast();
  const [modal, setModal] = useState(null);
  const [prescription, setPrescription] = useState('');
  const [smsPatient, setSmsPatient] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => setLoading(false), 800);
    return () => clearTimeout(timer);
  }, []);

  const openModal = (patient) => {
    setModal(patient);
    setPrescription('');
  };

  return (
    <div className="dashboard-page page-transition">
      <div className="dash-header">
        <h2 className="dash-title">{t('doctorDashboard')}</h2>
        <button className="export-csv-btn" onClick={() => showToast(t('csvDownloaded'))}>
          <Download size={16} />
          {t('exportCsv')}
        </button>
      </div>

      {/* Desktop Table */}
      <div className="dash-table-wrap glass">
        {loading ? (
          <div style={{ padding: '20px' }}>
            <div className="skeleton-row" />
            <div className="skeleton-row" />
            <div className="skeleton-row" />
          </div>
        ) : (
          <table className="dash-table">
            <thead>
              <tr>
                <th>{t('patientName')}</th>
                <th>{t('age')}</th>
                <th>{t('symptoms')}</th>
                <th>{t('risk')}</th>
                <th>{t('priority')}</th>
                <th>{t('time')}</th>
                <th>{t('actions')}</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((p) => (
                <tr key={p.id}>
                  <td className="td-name">{p.name}</td>
                  <td>{p.age}</td>
                  <td className="td-symptoms">{p.symptoms}</td>
                  <td>
                    <span className="risk-tag" style={{ '--tag-color': RISK_COLORS[p.risk] }}>
                      {p.risk}
                    </span>
                  </td>
                  <td className="td-priority">{PRIORITY[p.risk]}</td>
                  <td className="td-time">{p.time}</td>
                  <td>
                    <button className="review-btn" onClick={() => openModal(p)} aria-label="Review patient">
                      <Eye size={14} />
                      {t('review')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Mobile Cards */}
      <div className="dash-cards-mobile">
        {loading ? (
          <>
            <div className="skeleton-row" style={{ height: '120px' }} />
            <div className="skeleton-row" style={{ height: '120px' }} />
          </>
        ) : (
          sorted.map((p) => (
            <div className="patient-card glass" key={p.id}>
              <div className="patient-card-header">
                <span className="patient-card-name">{p.name}</span>
                <span className="risk-tag" style={{ '--tag-color': RISK_COLORS[p.risk] }}>
                  {p.risk}
                </span>
              </div>
              <div className="patient-card-body">
                <div className="patient-card-row">
                  <span>{t('age')}: {p.age}</span>
                  <span>{t('gender')}: {p.gender}</span>
                </div>
                <p className="patient-card-symptoms">{p.symptoms}</p>
                <div className="patient-card-row">
                  <span>{t('priority')}: {PRIORITY[p.risk]}</span>
                  <span>{p.time}</span>
                </div>
              </div>
              <button className="review-btn mobile-review" onClick={() => openModal(p)}>
                <Eye size={14} />
                {t('review')}
              </button>
            </div>
          ))
        )}
      </div>

      {/* Review Modal */}
      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal-content glass" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{t('patientDetails')}</h3>
              <button className="modal-close" onClick={() => setModal(null)} aria-label="Close modal">
                <X size={20} />
              </button>
            </div>

            <div className="modal-body">
              <div className="modal-detail-grid">
                <div className="modal-detail">
                  <span className="modal-label">{t('patientName')}</span>
                  <span className="modal-value">{modal.name}</span>
                </div>
                <div className="modal-detail">
                  <span className="modal-label">{t('age')}</span>
                  <span className="modal-value">{modal.age}</span>
                </div>
                <div className="modal-detail">
                  <span className="modal-label">{t('gender')}</span>
                  <span className="modal-value">{modal.gender}</span>
                </div>
                <div className="modal-detail">
                  <span className="modal-label">{t('risk')}</span>
                  <span className="risk-tag" style={{ '--tag-color': RISK_COLORS[modal.risk] }}>
                    {modal.risk}
                  </span>
                </div>
              </div>

              <div className="modal-detail full-width">
                <span className="modal-label">{t('symptoms')}</span>
                <span className="modal-value">{modal.symptoms}</span>
              </div>

              <div className="modal-prescription">
                <label>{t('prescription')}</label>
                <textarea
                  rows={4}
                  value={prescription}
                  onChange={(e) => setPrescription(e.target.value)}
                  placeholder={t('prescriptionPlaceholder')}
                />
              </div>
            </div>

            <div className="modal-footer">
              <button
                className="approve-btn"
                onClick={() => {
                  setSmsPatient(modal);
                  setModal(null);
                }}
              >
                {t('approveSms')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* SMS Slide-over Panel */}
      {smsPatient && (
        <SmsPanel patient={smsPatient} onClose={() => setSmsPatient(null)} />
      )}
    </div>
  );
}
