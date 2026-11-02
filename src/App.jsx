import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Home from './pages/Home';
import Triage from './pages/Triage';
import Results from './pages/Results';
import Dashboard from './pages/Dashboard';
import Navigation from './pages/Navigation';
import Booking from './pages/Booking';
import About from './pages/About';
import Chatbot from './pages/Chatbot';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Home />} />
          <Route path="/triage" element={<Triage />} />
          <Route path="/results" element={<Results />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/navigation" element={<Navigation />} />
          <Route path="/booking" element={<Booking />} />
          <Route path="/about" element={<About />} />
          <Route path="/chatbot" element={<Chatbot />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
