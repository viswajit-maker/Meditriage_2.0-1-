import { NavLink } from 'react-router-dom';
import {
  Home,
  ClipboardList,
  BarChart3,
  LayoutDashboard,
  MapPin,
  CalendarCheck,
  HeartPulse,
  MessageCircle,
} from 'lucide-react';
import { useApp } from '../context/AppContext';

const links = [
  { to: '/', icon: Home, label: 'home' },
  { to: '/triage', icon: ClipboardList, label: 'triage' },
  { to: '/results', icon: BarChart3, label: 'results' },
  { to: '/chatbot', icon: MessageCircle, label: 'chatbot' },
  { to: '/dashboard', icon: LayoutDashboard, label: 'dashboard' },
  { to: '/navigation', icon: MapPin, label: 'navigation' },
  { to: '/booking', icon: CalendarCheck, label: 'booking' },
];

export default function Sidebar() {
  const { t } = useApp();

  return (
    <aside className="sidebar glass">
      <div className="sidebar-logo">
        <HeartPulse size={22} />
        <span>MediTriage AI</span>
      </div>
      <nav className="sidebar-nav">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `sidebar-link${isActive ? ' active' : ''}`
            }
          >
            <Icon size={18} />
            {t(label)}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
