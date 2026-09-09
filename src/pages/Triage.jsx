import { useState, useMemo, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { User, Calendar, Stethoscope, Camera, Loader2, Mail, Mic, Square } from 'lucide-react';
import { useApp } from '../context/AppContext';

const EMERGENCY_KEYWORDS = [
  'chest pain',
  'unconsciousness',
  'severe bleeding',
  'breathing difficulty',
];

const LANG_OPTIONS = [
  { value: 'en', label: 'English' },
  { value: 'hi', label: 'Hindi' },
  { value: 'ta', label: 'Tamil' },
  { value: 'te', label: 'Telugu' },
  { value: 'kn', label: 'Kannada' },
];

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

export default function Triage() {
  const { t, setPatientData, setRiskResult } = useApp();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    name: '',
    age: '',
    gender: '',
    language: 'en',
    symptoms: '',
    email: '',
  });
  const [imagePreview, setImagePreview] = useState(null);
  const [cameraState, setCameraState] = useState('idle');
  const [cameraError, setCameraError] = useState('');
  const [showConsentModal, setShowConsentModal] = useState(false);
  const [consentGiven, setConsentGiven] = useState(false);
  const [consentCheckbox, setConsentCheckbox] = useState(false);
  const [submittingConsent, setSubmittingConsent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [submissionError, setSubmissionError] = useState('');
  const [voiceState, setVoiceState] = useState('idle');
  const [voiceError, setVoiceError] = useState('');
  
  const patientId = useMemo(() => crypto.randomUUID(), []);
  
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const cameraStreamRef = useRef(null);
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const recordingStartedAtRef = useRef(0);
  const maxRecordingTimerRef = useRef(null);
  const silenceTimerRef = useRef(null);
  const audioContextRef = useRef(null);
  const animationFrameRef = useRef(null);

  // Emergency detection (instant, no submit needed)
  const hasEmergency = useMemo(() => {
    const lower = form.symptoms.toLowerCase();
    return EMERGENCY_KEYWORDS.some((kw) => lower.includes(kw));
  }, [form.symptoms]);

  const updateField = (field, value) =>
    setForm((prev) => ({ ...prev, [field]: value }));

  const clearVoiceResources = () => {
    clearTimeout(maxRecordingTimerRef.current);
    clearTimeout(silenceTimerRef.current);
    cancelAnimationFrame(animationFrameRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    audioContextRef.current?.close();
    audioContextRef.current = null;
  };

  const stopCamera = () => {
    cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
    cameraStreamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraState('idle');
  };

  useEffect(() => () => {
    clearVoiceResources();
    stopCamera();
  }, []);

  // Attach stream to <video> element once it is in the DOM (after cameraState becomes 'live')
  useEffect(() => {
    if (cameraState === 'live' && videoRef.current && cameraStreamRef.current) {
      videoRef.current.srcObject = cameraStreamRef.current;
      videoRef.current.play().catch(() => {});
    }
  }, [cameraState]);

  const uploadVoiceRecording = async (blob, durationMs) => {
    if (blob.size < 1_000) {
      setVoiceError('No speech detected, please try again.');
      setVoiceState('idle');
      return;
    }

    setVoiceState('processing');
    const data = new FormData();
    data.append('audio', blob, 'symptoms.webm');
    data.append('duration_ms', String(durationMs));
    data.append('language_hint', form.language || 'auto');

    try {
      const response = await fetch(`${API_BASE_URL}/voice-symptoms`, { method: 'POST', body: data });
      let result;
      try {
        result = await response.json();
      } catch {
        if (!response.ok) throw new Error('Voice transcription service is unavailable. Please try again.');
        throw new Error('Voice transcription returned an unreadable response. Please try again.');
      }
      if (!response.ok || !result.symptoms_text) {
        throw new Error(result.error || 'Voice transcription could not be completed.');
      }
      updateField('symptoms', form.symptoms.trim() ? `${form.symptoms.trim()}, ${result.symptoms_text}` : result.symptoms_text);
    } catch (error) {
      setVoiceError(
        error instanceof TypeError
          ? 'Network failure while uploading the recording. Please check your connection and try again.'
          : error.message,
      );
    } finally {
      setVoiceState('idle');
    }
  };

  const stopVoiceRecording = () => {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop();
  };

  const startVoiceRecording = async () => {
    setVoiceError('');
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setVoiceError('Voice input is not supported in this browser. Please use a modern browser with microphone access.');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
      const recorder = new MediaRecorder(stream, { mimeType });
      recorderRef.current = recorder;
      chunksRef.current = [];
      recordingStartedAtRef.current = Date.now();
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const durationMs = Date.now() - recordingStartedAtRef.current;
        const recording = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        clearVoiceResources();
        uploadVoiceRecording(recording, durationMs);
      };

      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 512;
      audioContext.createMediaStreamSource(stream).connect(analyser);
      const samples = new Uint8Array(analyser.fftSize);
      let lastSpeechAt = Date.now();
      const watchForSilence = () => {
        analyser.getByteTimeDomainData(samples);
        const volume = samples.reduce((total, value) => total + Math.abs(value - 128), 0) / samples.length;
        if (volume > 3) lastSpeechAt = Date.now();
        if (Date.now() - lastSpeechAt > 2_500) {
          stopVoiceRecording();
          return;
        }
        animationFrameRef.current = requestAnimationFrame(watchForSilence);
      };

      recorder.start();
      setVoiceState('listening');
      maxRecordingTimerRef.current = setTimeout(stopVoiceRecording, 30_000);
      animationFrameRef.current = requestAnimationFrame(watchForSilence);
    } catch (error) {
      if (error?.name === 'NotAllowedError' || error?.name === 'SecurityError') {
        setVoiceError('Microphone permission was denied. Allow microphone access and try again.');
      } else if (error?.name === 'NotFoundError') {
        setVoiceError('No microphone was found. Connect a microphone and try again.');
      } else {
        setVoiceError('Unable to start the microphone. Please try again.');
      }
      clearVoiceResources();
      setVoiceState('idle');
    }
  };

  const startCamera = async () => {
    setCameraError('');
    if (!consentGiven) {
      setShowConsentModal(true);
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError('Live camera capture is not supported in this browser.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      cameraStreamRef.current = stream;
      // Set state FIRST so React renders the <video> element into the DOM,
      // then the useEffect below attaches srcObject once the element exists.
      setCameraState('live');
    } catch (error) {
      if (error?.name === 'NotAllowedError' || error?.name === 'SecurityError') {
        setCameraError('Camera permission was denied. Allow camera access and try again.');
      } else if (error?.name === 'NotFoundError') {
        setCameraError('No camera was found. Connect a camera and try again.');
      } else {
        setCameraError('Unable to open the camera. Please try again.');
      }
      stopCamera();
    }
  };

  const capturePhoto = () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !video.videoWidth) {
      setCameraError('The camera is not ready yet. Please try again.');
      return;
    }
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
    setImagePreview(canvas.toDataURL('image/jpeg', 0.9));
    cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
    cameraStreamRef.current = null;
    video.srcObject = null;
    setCameraState('captured');
  };

  const handleConsentSubmit = async () => {
    if (!consentCheckbox) return;
    setSubmittingConsent(true);
    try {
      const response = await fetch(`${API_BASE_URL}/consent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          patient_id: patientId,
          purpose: 'medical_triage',
          consent_version: '1.0'
        })
      });
      if (!response.ok) throw new Error('Failed to record consent');
      
      setConsentGiven(true);
      setShowConsentModal(false);
      
      // Now that consent is recorded, we can start the camera
      // We must call startCamera in the next tick so the state updates and videoRef is not null? 
      // Wait, startCamera just sets cameraStreamRef and sets cameraState='live'. The useEffect will hook it up.
      // So we can just call it, but we need to wait for state to settle? No, startCamera is async.
      setTimeout(() => startCamera(), 0);
    } catch (err) {
      setCameraError('Error recording consent. Please try again.');
      setShowConsentModal(false);
    } finally {
      setSubmittingConsent(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setSubmissionError('');
    const patientPayload = {
      name: form.name,
      age: parseInt(form.age),
      gender: `${form.gender.charAt(0).toUpperCase()}${form.gender.slice(1)}`,
      symptoms: form.symptoms,
      email: form.email,
    };

    try {
      const response = await fetch(`${API_BASE_URL}/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(patientPayload),
      });
      let result;
      try {
        result = await response.json();
      } catch (jsonErr) {
        throw new Error('Invalid response from server. Please try again.');
      }

      if (!response.ok || result.error) {
        throw new Error(result.error || 'Assessment could not be completed.');
      }
      setPatientData(patientPayload);
      setRiskResult(result);
      navigate('/results');
    } catch (error) {
      if (error instanceof TypeError && error.message.includes('Failed to fetch')) {
        setSubmissionError("Couldn't reach the server, please try again.");
      } else {
        setSubmissionError(error.message || 'Assessment could not be completed. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="triage-page page-transition">
      {/* Consent Modal Overlay */}
      {showConsentModal && (
        <div className="modal-overlay">
          <div className="modal-content glass">
            <h3>Privacy & Consent</h3>
            <p>
              Before we activate your camera, we need your permission. Your photo will be securely encrypted and used only for medical triage purposes by our assigned medical staff.
            </p>
            <label className="consent-label">
              <input 
                type="checkbox" 
                checked={consentCheckbox} 
                onChange={(e) => setConsentCheckbox(e.target.checked)} 
              />
              I consent to my photo being used for medical triage purposes.
            </label>
            <div className="modal-actions">
              <button 
                type="button" 
                className="camera-action primary" 
                onClick={handleConsentSubmit}
                disabled={!consentCheckbox || submittingConsent}
              >
                {submittingConsent ? <Loader2 size={16} className="spinner" /> : 'Accept & Open Camera'}
              </button>
              <button 
                type="button" 
                className="camera-action" 
                onClick={() => { setShowConsentModal(false); setConsentCheckbox(false); }}
                disabled={submittingConsent}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="intake-card glass">
        <h2 className="intake-title">{t('patientIntake')}</h2>

        <form onSubmit={handleSubmit} className="intake-form">
          {/* Full Name */}
          <div className="form-group">
            <label htmlFor="name-input">{t('name')}</label>
            <div className="input-wrapper">
              <User size={18} className="input-icon" />
              <input
                id="name-input"
                type="text"
                required
                value={form.name}
                onChange={(e) => updateField('name', e.target.value)}
                placeholder={t('name')}
              />
            </div>
          </div>

          {/* Age */}
          <div className="form-group">
            <label htmlFor="age-input">{t('age')}</label>
            <div className="input-wrapper">
              <Calendar size={18} className="input-icon" />
              <input
                id="age-input"
                type="number"
                required
                min="0"
                max="150"
                value={form.age}
                onChange={(e) => updateField('age', e.target.value)}
                placeholder={t('age')}
              />
            </div>
          </div>

          {/* Gender */}
          <div className="form-group">
            <label>{t('gender')}</label>
            <div className="gender-radios">
              {['male', 'female', 'other'].map((g) => (
                <label
                  key={g}
                  className={`gender-option${form.gender === g ? ' selected' : ''}`}
                >
                  <input
                    type="radio"
                    name="gender"
                    value={g}
                    checked={form.gender === g}
                    onChange={() => updateField('gender', g)}
                  />
                  {t(g)}
                </label>
              ))}
            </div>
          </div>

          {/* Language */}
          <div className="form-group">
            <label htmlFor="lang-select">{t('language')}</label>
            <select
              id="lang-select"
              className="styled-select"
              value={form.language}
              onChange={(e) => updateField('language', e.target.value)}
            >
              {LANG_OPTIONS.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>

          {/* Symptoms */}
          <div className="form-group">
            <label htmlFor="symp-textarea">{t('symptoms')}</label>
            <div className="input-wrapper textarea-wrapper">
              <Stethoscope size={18} className="input-icon textarea-icon" />
              <textarea
                id="symp-textarea"
                required
                rows={5}
                value={form.symptoms}
                onChange={(e) => updateField('symptoms', e.target.value)}
                placeholder={t('symptomsPlaceholder')}
                disabled={voiceState === 'processing'}
              />
              <button
                type="button"
                className={`voice-button ${voiceState === 'listening' ? 'listening' : ''}`}
                onClick={voiceState === 'listening' ? stopVoiceRecording : startVoiceRecording}
                disabled={voiceState === 'processing'}
                aria-label={voiceState === 'listening' ? 'Stop recording symptoms' : 'Record symptoms by voice'}
                title={voiceState === 'listening' ? 'Stop recording' : 'Speak symptoms'}
              >
                {voiceState === 'processing' ? <Loader2 size={18} className="spinner" /> : voiceState === 'listening' ? <Square size={16} fill="currentColor" /> : <Mic size={19} />}
              </button>
            </div>
            {voiceState === 'listening' && (
              <div className="voice-status" role="status">
                <span className="voice-pulse" /> Listening… tap the square to stop
              </div>
            )}
            {voiceState === 'processing' && (
              <div className="voice-status" role="status">
                <Loader2 size={16} className="spinner" /> Translating your symptoms into English…
              </div>
            )}
            {voiceError && <div className="voice-error" role="alert">{voiceError}</div>}
            {hasEmergency && (
              <div className="emergency-alert">
                {t('emergencyAlert')}
              </div>
          )}

          {submissionError && (
            <div className="emergency-alert" role="alert">
              {submissionError}
            </div>
          )}
          </div>

          {/* Email Address */}
          <div className="form-group">
            <label htmlFor="email-input">Email Address</label>
            <div className="input-wrapper">
              <Mail size={18} className="input-icon" />
              <input
                id="email-input"
                type="email"
                required
                value={form.email}
                onChange={(e) => updateField('email', e.target.value)}
                placeholder="Enter your email to receive report"
              />
            </div>
          </div>

          {/* Live Camera Capture */}
          <div className="form-group">
            <label>Capture Live Photo</label>
            {cameraState === 'live' ? (
              <div className="camera-capture">
                <video ref={videoRef} className="camera-preview" autoPlay muted playsInline aria-label="Live camera preview" />
                <div className="camera-actions">
                  <button type="button" className="camera-action primary" onClick={capturePhoto}>
                    <Camera size={18} /> Capture Photo
                  </button>
                  <button type="button" className="camera-action" onClick={stopCamera}>Cancel</button>
                </div>
              </div>
            ) : imagePreview ? (
              <div className="camera-capture">
                <img src={imagePreview} alt="Captured patient" className="camera-preview" />
                <div className="camera-actions">
                  <span className="camera-captured-label">Photo captured successfully</span>
                  <button type="button" className="camera-action" onClick={() => { setImagePreview(null); startCamera(); }}>Retake</button>
                </div>
              </div>
            ) : (
              <button type="button" className="camera-launch" onClick={startCamera} aria-label="Open camera to capture live photo">
                <Camera size={22} /> Open Camera &amp; Capture Live Photo
              </button>
            )}
            <canvas ref={canvasRef} hidden />
            {cameraError && <div className="voice-error" role="alert">{cameraError}</div>}
          </div>

          {/* Submit */}
          <button
            type="submit"
            className="submit-btn"
            disabled={loading}
          >
            {loading ? (
              <span className="loading-state">
                <Loader2 size={20} className="spinner" />
                {t('assessing')}
              </span>
            ) : (
              t('assessRisk')
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
