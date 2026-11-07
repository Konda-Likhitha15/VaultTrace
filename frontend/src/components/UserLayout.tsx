import type { ReactNode } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAppContext } from '../context/AppContext';

export function UserLayout({ children }: { children: ReactNode }) {
  const { user, logout } = useAppContext();
  const navigate = useNavigate();
  const navigation: Array<[string, string]> = user?.role === 'Owner'
    ? [['/owner/dashboard', 'Dashboard'], ['/documents', 'My documents'], ['/documents/upload', 'Upload documents'], ['/documents/search', 'Search documents'], ['/documents/categories', 'Categories'], ['/documents/shared-by-me', 'Shared by me'], ['/documents/deleted', 'Deleted documents'], ['/profile', 'Profile']]
    : [['/viewer/dashboard', 'Dashboard'], ['/documents', 'My documents'], ['/documents/shared', 'Shared with me'], ['/documents/search', 'Search documents'], ['/documents/categories', 'Categories'], ['/profile', 'Profile']];

  async function signOut() {
    const revoked = await logout();
    navigate('/login', { replace: true, state: revoked ? undefined : { notice: 'You were signed out on this device, but server revocation could not be confirmed. The access token will expire automatically.' } });
  }

  return <div className="min-h-screen lg:grid lg:grid-cols-[240px_1fr]">
    <aside className="border-b border-gray-200 bg-white p-4 lg:min-h-screen lg:border-b-0 lg:border-r lg:p-6">
      <p className="font-semibold text-indigo-700">VaultTrace</p>
      <p className="mt-1 text-sm text-gray-500">{user?.role} workspace</p>
      <nav aria-label="User navigation" className="mt-5 flex gap-2 overflow-x-auto lg:flex-col">
        {navigation.map(([to, label]) => <NavLink key={to} end={to === '/documents'} to={to} className={({ isActive }) => `whitespace-nowrap rounded px-3 py-2 text-sm ${isActive ? 'bg-indigo-50 font-semibold text-indigo-800' : 'text-gray-700 hover:bg-gray-100'}`}>{label}</NavLink>)}
      </nav>
      <button className="mt-5 rounded border border-gray-300 px-3 py-2 text-sm" onClick={() => void signOut()}>Sign out</button>
      <p className="mt-4 hidden break-all text-xs text-gray-500 lg:block">Signed in as {user?.email}</p>
    </aside>
    <div className="min-w-0 p-4 sm:p-8">{children}</div>
  </div>;
}
