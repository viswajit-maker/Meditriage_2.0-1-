import { useState } from 'react';
import { Scissors, CalendarDays, Clock, CheckCircle, Loader2 } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { useToast } from '../context/ToastContext';

const TIME_SLOTS = ['9:00 AM', '10:30 AM', '12:00 PM', '2:00 PM', '3:30 PM', '5:00 PM'];

const FALLBACK_HOSPITAL = { name: 'Apollo Clinic Tambaram' };

export default function Booking() {
  const { t, patientData, selectedHospital } = useApp();
  const { showToast } = useToast();
  const hospital = selectedHospital || FALLBACK_HOSPITAL;

  const [date, setDate] = useState('');
  const [timeSlot, setTimeSlot] = useState('');
  const [loading, setLoading] = useState(false);
  const [confirmed, setConfirmed] = useState(false);

  const handleConfirm = (e) => {
    e.preventDefault();
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      setConfirmed(true);
      showToast(t('appointmentConfirmed'));
    }, 1500);
  };

  if (confirmed) {
    return (
      <div className="booking-page page-transition">
        <div className="ticket-card">
          <div className="ticket-scissor">
            <Scissors size={16} />
            <div className="ticket-dashed" />
            <Scissors size={16} style={{ transform: 'scaleX(-1)' }} />
          </div>
          <div className="ticket-body">
            <div className="ticket-check">
              <CheckCircle size={40} />
            </div>
            <h2 className="ticket-title">{t('appointmentConfirmed')}</h2>
            <div className="ticket-details">
              <div className="ticket-row">
                <span className="ticket-label">Hospital</span>
                <span className="ticket-value">{hospital.name}</span>
              </div>
              <div className="ticket-row">
                <span className="ticket-label">Date</span>
                <span className="ticket-value">{date}</span>
              </div>
              <div className="ticket-row">
                <span className="ticket-label">Time</span>
                <span className="ticket-value">{timeSlot}</span>
              </div>
              <div className="ticket-row">
                <span className="ticket-label">Patient</span>
                <span className="ticket-value">{patientData?.name || 'Patient'}</span>
              </div>
            </div>
          </div>
          <div className="ticket-notice">
            <p>{t('bookingNotice')}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="booking-page page-transition">
      <div className="booking-card glass">
        <h2 className="booking-title">{t('appointmentBooking')}</h2>

        <div className="booking-hospital">
          <span className="booking-hospital-label">Hospital</span>
          <span className="booking-hospital-name">{hospital.name}</span>
        </div>

        <form onSubmit={handleConfirm} className="booking-form">
          {/* Date Picker */}
          <div className="form-group">
            <label>{t('selectDate')}</label>
            <div className="input-wrapper">
              <CalendarDays size={18} className="input-icon" />
              <input
                type="date"
                required
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="styled-date"
              />
            </div>
          </div>

          {/* Time Slots */}
          <div className="form-group">
            <label>{t('selectTime')}</label>
            <div className="time-slots">
              {TIME_SLOTS.map((slot) => (
                <button
                  key={slot}
                  type="button"
                  className={`time-pill${timeSlot === slot ? ' active' : ''}`}
                  onClick={() => setTimeSlot(slot)}
                >
                  <Clock size={14} />
                  {slot}
                </button>
              ))}
            </div>
          </div>

          {/* Pre-filled Patient Info */}
          {patientData && (
            <div className="prefilled-info glass">
              <div className="prefilled-row">
                <span className="prefilled-label">{t('name')}</span>
                <span className="prefilled-value">{patientData.name}</span>
              </div>
              <div className="prefilled-row">
                <span className="prefilled-label">{t('age')}</span>
                <span className="prefilled-value">{patientData.age}</span>
              </div>
            </div>
          )}

          <button
            type="submit"
            className="submit-btn"
            disabled={loading || !date || !timeSlot}
          >
            {loading ? (
              <span className="loading-state">
                <Loader2 size={20} className="spinner" />
                {t('confirming')}
              </span>
            ) : (
              t('confirmBooking')
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
