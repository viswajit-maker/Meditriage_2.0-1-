import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopNavbar from './TopNavbar';
import BottomTabBar from './BottomTabBar';

export default function Layout() {
  return (
    <div className="app-layout">
      <Sidebar />
      <div className="main-area">
        <TopNavbar />
        <main className="page-content">
          <Outlet />
        </main>
        <BottomTabBar />
      </div>
    </div>
  );
}
