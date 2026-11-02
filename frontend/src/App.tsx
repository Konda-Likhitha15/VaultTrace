import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { useAppContext } from './context/AppContext';
import { AdminApplicationsPage } from './pages/AdminApplicationsPage';
import { AdminDashboardPage } from './pages/AdminDashboardPage';
import { AdminUsersPage } from './pages/AdminUsersPage';
import { AdminLayout } from './components/AdminLayout';
import { DashboardPage } from './pages/DashboardPage';
import { LoginPage } from './pages/LoginPage';
import { SignupPage } from './pages/SignupPage';
import { ForgotPasswordPage } from './pages/ForgotPasswordPage';
import { ResetPasswordPage } from './pages/ResetPasswordPage';

function homeForRole(role: string): string {
  if (role === 'Administrator') return '/admin/dashboard';
  if (role === 'Owner') return '/owner/dashboard';
  return '/viewer/dashboard';
}

function SignedInHome() {
  const { user } = useAppContext();
  return user ? <Navigate to={homeForRole(user.role)} replace /> : <Navigate to="/login" replace />;
}

function ProtectedDashboard() {
  const { user } = useAppContext();
  const { pathname } = useLocation();
  const expectedRole = pathname.startsWith('/owner/') ? 'Owner' : 'Viewer';
  return user?.role === expectedRole ? <DashboardPage /> : <SignedInHome />;
}

function ProtectedAdmin() {
  const { user } = useAppContext();
  if (!user) return <Navigate to="/login" replace />;
  return user.role === 'Administrator' ? <AdminLayout><Outlet /></AdminLayout> : <SignedInHome />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/admin" element={<ProtectedAdmin />}>
        <Route path="dashboard" element={<AdminDashboardPage />} />
        <Route path="users" element={<AdminUsersPage mode="all" />} />
        <Route path="roles" element={<AdminUsersPage mode="roles" />} />
        <Route path="accounts" element={<AdminUsersPage mode="accounts" />} />
        <Route path="applications" element={<AdminApplicationsPage />} />
      </Route>
      <Route path="/owner/dashboard" element={<ProtectedDashboard />} />
      <Route path="/viewer/dashboard" element={<ProtectedDashboard />} />
      <Route path="/" element={<SignedInHome />} />
      <Route path="*" element={<SignedInHome />} />
    </Routes>
  );
}
