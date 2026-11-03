import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppContext } from '../context/AppContext';

const roleDescriptions: Record<string, string> = {
  Administrator: 'You can administer VaultTrace access and configuration.',
  Owner: 'You can manage documents and access you own.',
  Viewer: 'You can view documents assigned to your account.',
};

export function DashboardPage() {
  const { user, refreshUser } = useAppContext();
  const navigate = useNavigate();
  const [message, setMessage] = useState('');

  useEffect(() => {
    void refreshUser().catch(() => setMessage('Your session could not be refreshed. Sign in again.'));
  }, [refreshUser]);

  return (
    <main className="mx-auto w-full max-w-4xl">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">VaultTrace</p><h1 className="mt-1 text-3xl font-bold">Dashboard</h1>
      </header>
      {user && <section id="profile" className="mt-8 rounded-xl bg-white p-6 shadow-sm">
        <h2 className="text-xl font-semibold">Welcome, {user.email}</h2>
        <p className="mt-2 text-gray-600">Role: <strong>{user.role}</strong></p>
        <p className="mt-3 text-gray-700">{roleDescriptions[user.role] ?? 'Your assigned VaultTrace role determines available access.'}</p>
      </section>}
      {message && <p className="mt-4 text-sm text-amber-800" role="alert">{message}</p>}
      <section className="mt-6 rounded-xl border border-dashed border-gray-300 p-6 text-gray-600">
        <h2 className="text-lg font-semibold text-gray-900">Document workspace</h2>
        <p className="mt-1">Browse and manage documents available to your account.</p>
        <button className="mt-4 rounded bg-indigo-700 px-4 py-2 font-semibold text-white" type="button" onClick={() => navigate(user?.role === 'Owner' ? '/documents/upload' : '/documents')}>{user?.role === 'Owner' ? 'Upload a document' : 'Open documents'}</button>
      </section>
    </main>
  );
}
