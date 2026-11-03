import { useState, useRef, useEffect } from 'react';
import { MessageCircle, Send, RotateCcw, AlertTriangle, Activity, Stethoscope } from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8001';

export default function Chatbot() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: "👋 Hello! I'm the MediTriage AI assistant. Describe your symptoms in detail and I'll help assess your condition.\n\nFor example: *\"I have a persistent headache, mild fever, and feel very tired for the past 3 days.\"*",
    },
  ]);
  const [input, setInput] = useState('');
  const [sessionId, setSessionId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [diagnosis, setDiagnosis] = useState(null);
  const [turn, setTurn] = useState(0);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (!loading) inputRef.current?.focus();
  }, [loading]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setMessages((prev) => [...prev, { role: 'user', text }]);
    setInput('');
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/chatbot/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: text }),
      });

      if (!res.ok) throw new Error('Server error');

      const data = await res.json();
      setSessionId(data.session_id);
      setTurn(data.turn);
      setMessages((prev) => [...prev, { role: 'assistant', text: data.reply }]);

      if (data.is_final && data.diagnosis) {
        setDiagnosis(data.diagnosis);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: '❌ Sorry, I couldn\'t connect to the server. Please make sure the chatbot backend is running on port 8001.',
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const resetChat = async () => {
    if (sessionId) {
      try {
        await fetch(`${API_BASE}/chatbot/reset`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId, message: '' }),
        });
      } catch {}
    }
    setMessages([
      {
        role: 'assistant',
        text: "👋 Hello! I'm the MediTriage AI assistant. Describe your symptoms in detail and I'll help assess your condition.\n\nFor example: *\"I have a persistent headache, mild fever, and feel very tired for the past 3 days.\"*",
      },
    ]);
    setSessionId(null);
    setDiagnosis(null);
    setTurn(0);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const riskColor = (level) => {
    if (level === 'High') return 'var(--high)';
    if (level === 'Medium') return 'var(--medium)';
    return 'var(--low)';
  };

  const formatMessage = (text) => {
    // Simple markdown-like formatting
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/---/g, '<hr style="border:none;border-top:1px solid rgba(100,116,139,0.25);margin:12px 0"/>')
      .replace(/\n/g, '<br/>');
  };

  return (
    <div className="chatbot-page page-transition">
      <div className="chatbot-container glass">
        {/* Header */}
        <div className="chatbot-header">
          <div className="chatbot-header-left">
            <div className="chatbot-avatar">
              <Stethoscope size={20} />
            </div>
            <div>
              <h2 className="chatbot-title">MediTriage AI Chat</h2>
              <span className="chatbot-status">
                <span className="status-dot" />
                {loading ? 'Analyzing...' : 'Online'}
              </span>
            </div>
          </div>
          <button className="chatbot-reset-btn" onClick={resetChat} title="New conversation">
            <RotateCcw size={16} />
            New Chat
          </button>
        </div>

        {/* Messages */}
        <div className="chatbot-messages">
          {messages.map((msg, i) => (
            <div key={i} className={`chat-bubble ${msg.role}`}>
              {msg.role === 'assistant' && (
                <div className="bubble-avatar">
                  <Activity size={14} />
                </div>
              )}
              <div
                className="bubble-content"
                dangerouslySetInnerHTML={{ __html: formatMessage(msg.text) }}
              />
            </div>
          ))}

          {loading && (
            <div className="chat-bubble assistant">
              <div className="bubble-avatar">
                <Activity size={14} />
              </div>
              <div className="bubble-content typing-indicator">
                <span /><span /><span />
              </div>
            </div>
          )}

          {/* Diagnosis Card */}
          {diagnosis && (
            <div className="diagnosis-card glass" style={{ borderColor: riskColor(diagnosis.risk_level) }}>
              <div className="diagnosis-header">
                <AlertTriangle size={18} style={{ color: riskColor(diagnosis.risk_level) }} />
                <h3>Diagnosis Summary</h3>
              </div>

              <div className="diagnosis-main">
                <div className="diagnosis-disease">{diagnosis.predicted_disease}</div>
                <div className="diagnosis-confidence">
                  <div className="confidence-bar">
                    <div
                      className="confidence-fill"
                      style={{
                        width: `${diagnosis.confidence}%`,
                        background: riskColor(diagnosis.risk_level),
                      }}
                    />
                  </div>
                  <span>{diagnosis.confidence}% confidence</span>
                </div>
                <span
                  className="risk-badge"
                  style={{
                    background: `${riskColor(diagnosis.risk_level)}22`,
                    color: riskColor(diagnosis.risk_level),
                    border: `1px solid ${riskColor(diagnosis.risk_level)}`,
                  }}
                >
                  {diagnosis.risk_level} Risk
                </span>
              </div>

              {diagnosis.differential && diagnosis.differential.length > 1 && (
                <div className="diagnosis-differential">
                  <h4>Differential Diagnosis</h4>
                  {diagnosis.differential.map((d, i) => (
                    <div key={i} className="diff-item">
                      <span className="diff-name">{d.disease}</span>
                      <span className="diff-conf">{d.confidence}%</span>
                    </div>
                  ))}
                </div>
              )}

              <div className="diagnosis-disclaimer">
                ⚕️ This is an AI-assisted preliminary assessment. Always consult a qualified healthcare professional.
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="chatbot-input-area">
          {diagnosis ? (
            <button className="chatbot-restart-btn" onClick={resetChat}>
              <MessageCircle size={16} />
              Start New Assessment
            </button>
          ) : (
            <div className="chatbot-input-wrapper">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  turn === 0
                    ? 'Describe your symptoms...'
                    : 'Answer the follow-up question...'
                }
                disabled={loading}
                rows={1}
              />
              <button
                className="chatbot-send-btn"
                onClick={sendMessage}
                disabled={!input.trim() || loading}
              >
                <Send size={18} />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
