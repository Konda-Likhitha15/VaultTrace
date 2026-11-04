import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAppContext } from '../context/AppContext';

const links = [
  ['/admin/dashboard', 'Overview'],
  ['/admin/users', 'All users'],
  ['/admin/applications', 'Applications'],
  ['/admin/roles', 'Roles'],
  ['/admin/accounts', 'Accounts'],
  ['/admin/documents', 'Documents & audit'],
  ['/admin/audit-trail', 'Audit Trail'],
] as const;

export function AdminLayout({ children }: { children?: ReactNode }) {
  const { user, logout } = useAppContext();
  const navigate = useNavigate();

  async function signOut() {
    try {
      await logout();
    } finally {
      navigate('/login', { replace: true });
    }
  }

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[240px_1fr]">
      <aside className="border-b border-gray-200 bg-white p-4 lg:min-h-screen lg:border-b-0 lg:border-r lg:p-6">
        <div className="flex items-center justify-between lg:block">
          <div><p className="font-semibold text-indigo-700">VaultTrace</p><p className="mt-1 text-sm text-gray-500">Administration</p></div>
          <button className="rounded border border-gray-300 px-3 py-2 text-sm lg:mt-6" onClick={() => void signOut()}>Sign out</button>
        </div>
        <nav aria-label="Admin navigation" className="mt-5 flex gap-2 overflow-x-auto lg:flex-col">
          {links.map(([to, label]) => <NavLink key={to} to={to} className={({ isActive }) => `whitespace-nowrap rounded px-3 py-2 text-sm ${isActive ? 'bg-indigo-50 font-semibold text-indigo-800' : 'text-gray-700 hover:bg-gray-100'}`}>{label}</NavLink>)}
        </nav>
        <p className="mt-6 hidden break-all text-xs text-gray-500 lg:block">Signed in as {user?.email}</p>
      </aside>
      <div className="min-w-0 p-4 sm:p-8">{children ?? <Outlet />}</div>
    </div>
  );
}
