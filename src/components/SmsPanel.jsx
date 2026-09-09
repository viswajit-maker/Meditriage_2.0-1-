import { useState } from 'react';
import { X, Phone, Send, CheckCircle, Loader2 } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { useToast } from '../context/ToastContext';

const SMS_LOG = [
  { name: 'Priya Sharma', time: '10:34 AM', status: 'delivered' },
  { name: 'Ravi Kumar', time: '10:50 AM', status: 'delivered' },
  { name: 'Kavitha R', time: '11:25 AM', status: 'pending' },
];

export default function SmsPanel({ patient, onClose }) {
  const { t } = useApp();
  const { showToast } = useToast();
  const [phone, setPhone] = useState('');
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  const smsText = `MediTriage Alert:\nPatient: ${patient?.name || 'N/A'} | Age: ${patient?.age || 'N/A'}\nSymptoms: ${patient?.symptoms || 'N/A'}\nRisk Level: ${patient?.risk || 'HIGH'} ⚠️\nSuggested: Rest, consult cardiologist\n— MediTriage AI System`;

  const handleSend = () => {
    setSending(true);
    setTimeout(() => {
      setSending(false);
      setSent(true);
      showToast(t('smsDispatched'));
    }, 1000);
  };

  return (
    <div className="sms-overlay" onClick={onClose}>
      <div className="sms-panel glass" onClick={(e) => e.stopPropagation()}>
        <div className="sms-header">
          <h3>{t('smsPanel')}</h3>
          <button className="modal-close" onClick={onClose} aria-label="Close SMS panel">
            <X size={20} />
          </button>
        </div>

        <div className="sms-body">
          {/* Phone Input */}
          <div className="form-group">
            <label>{t('phoneNumber')}</label>
            <div className="input-wrapper">
              <Phone size={18} className="input-icon" />
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+91 98765 43210"
              />
            </div>
          </div>

          {/* SMS Preview */}
          <div className="form-group">
            <label>{t('smsPreview')}</label>
            <pre className="sms-preview">{smsText}</pre>
          </div>

          {/* Send Button / Success */}
          {sent ? (
            <div className="sms-success">
              <CheckCircle size={32} />
              <span>{t('smsDispatched')}</span>
            </div>
          ) : (
            <button
              className="submit-btn"
              onClick={handleSend}
              disabled={sending || !phone}
            >
              {sending ? (
                <span className="loading-state">
                  <Loader2 size={20} className="spinner" />
                  {t('sending')}
                </span>
              ) : (
                <>
                  <Send size={16} />
                  {t('sendSms')}
                </>
              )}
            </button>
          )}

          {/* SMS Log */}
          <div className="sms-log-section">
            <h4>{t('smsLog')}</h4>
            <table className="sms-log-table">
              <thead>
                <tr>
                  <th>{t('patientName')}</th>
                  <th>{t('time')}</th>
                  <th>{t('status')}</th>
                </tr>
              </thead>
              <tbody>
                {SMS_LOG.map((entry, i) => (
                  <tr key={i}>
                    <td>{entry.name}</td>
                    <td>{entry.time}</td>
                    <td>
                      <span className={`sms-status ${entry.status}`}>
                        {t(entry.status)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
