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
import { DocumentsPage } from './pages/DocumentsPage';
import { DocumentUploadPage } from './pages/DocumentUploadPage';
import { DocumentSearchPage } from './pages/DocumentSearchPage';
import { DocumentCategoriesPage } from './pages/DocumentCategoriesPage';
import { SharedWithMePage } from './pages/SharedWithMePage';
import { SharedByMePage } from './pages/SharedByMePage';
import { DeletedDocumentsPage } from './pages/DeletedDocumentsPage';
import { AdminDocumentsPage } from './pages/AdminDocumentsPage';
import { UserLayout } from './components/UserLayout';

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
  return user?.role === expectedRole ? <UserLayout><DashboardPage /></UserLayout> : <SignedInHome />;
}

function ProtectedAdmin() {
  const { user } = useAppContext();
  if (!user) return <Navigate to="/login" replace />;
  return user.role === 'Administrator' ? <AdminLayout><Outlet /></AdminLayout> : <SignedInHome />;
}

function ProtectedDocuments() {
  const { user } = useAppContext();
  return user ? <UserLayout><DocumentsPage /></UserLayout> : <Navigate to="/login" replace />;
}

function ProtectedDocumentUpload() {
  const { user } = useAppContext();
  if (!user) return <Navigate to="/login" replace />;
  return user.role === 'Owner'
    ? <UserLayout><DocumentUploadPage /></UserLayout>
    : <Navigate to="/documents" replace />;
}

function ProtectedUserDocumentPage({ children, ownerOnly = false }: { children: React.ReactNode; ownerOnly?: boolean }) {
  const { user } = useAppContext();
  if (!user) return <Navigate to="/login" replace />;
  if (ownerOnly && user.role !== 'Owner') return <SignedInHome />;
  return <UserLayout>{children}</UserLayout>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/documents" element={<ProtectedDocuments />} />
      <Route path="/documents/upload" element={<ProtectedDocumentUpload />} />
      <Route path="/documents/search" element={<ProtectedUserDocumentPage><DocumentSearchPage /></ProtectedUserDocumentPage>} />
      <Route path="/documents/categories" element={<ProtectedUserDocumentPage><DocumentCategoriesPage /></ProtectedUserDocumentPage>} />
      <Route path="/documents/shared" element={<ProtectedUserDocumentPage><SharedWithMePage /></ProtectedUserDocumentPage>} />
      <Route path="/documents/shared-by-me" element={<ProtectedUserDocumentPage ownerOnly><SharedByMePage /></ProtectedUserDocumentPage>} />
      <Route path="/documents/deleted" element={<ProtectedUserDocumentPage ownerOnly><DeletedDocumentsPage /></ProtectedUserDocumentPage>} />
      <Route path="/admin" element={<ProtectedAdmin />}>
        <Route path="dashboard" element={<AdminDashboardPage />} />
        <Route path="users" element={<AdminUsersPage mode="all" />} />
        <Route path="roles" element={<AdminUsersPage mode="roles" />} />
        <Route path="accounts" element={<AdminUsersPage mode="accounts" />} />
        <Route path="applications" element={<AdminApplicationsPage />} />
        <Route path="documents" element={<AdminDocumentsPage />} />
      </Route>
      <Route path="/owner/dashboard" element={<ProtectedDashboard />} />
      <Route path="/viewer/dashboard" element={<ProtectedDashboard />} />
      <Route path="/dashboard" element={<SignedInHome />} />
      <Route path="/" element={<SignedInHome />} />
      <Route path="*" element={<SignedInHome />} />
    </Routes>
  );
}
