import { NavLink } from 'react-router-dom';
import {
  Home,
  ClipboardList,
  BarChart3,
  LayoutDashboard,
  MessageCircle,
} from 'lucide-react';
import { useApp } from '../context/AppContext';

const tabs = [
  { to: '/', icon: Home, label: 'home' },
  { to: '/triage', icon: ClipboardList, label: 'triage' },
  { to: '/chatbot', icon: MessageCircle, label: 'chatbot' },
  { to: '/results', icon: BarChart3, label: 'results' },
  { to: '/dashboard', icon: LayoutDashboard, label: 'dashboard' },
];

export default function BottomTabBar() {
  const { t } = useApp();

  return (
    <nav className="bottom-tab-bar glass">
      {tabs.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) =>
            `tab-item${isActive ? ' active' : ''}`
          }
        >
          <Icon size={20} />
          {t(label)}
        </NavLink>
      ))}
    </nav>
  );
}
