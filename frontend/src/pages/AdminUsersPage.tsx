import { useEffect, useState } from 'react';
import axios from 'axios';
import { useAppContext } from '../context/AppContext';
import { getAdminUsers, updateAdminUserRole, updateAdminUserStatus } from '../services/api';
import type { AdminUser } from '../types';

type ManagementMode = 'all' | 'roles' | 'accounts';
const labels: Record<ManagementMode, string> = { all: 'All users', roles: 'Role management', accounts: 'Account management' };

export function AdminUsersPage({ mode }: { mode: ManagementMode }) {
  const { token, user: currentUser } = useAppContext();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function refresh() {
    if (!token) return;
    setLoading(true);
    try {
      setUsers(await getAdminUsers(token));
      setError('');
    } catch (reason) {
      setError(axios.isAxiosError(reason) ? String(reason.response?.data?.detail ?? 'Could not load users.') : 'Could not load users.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, [token]);

  async function setRole(target: AdminUser, role: 'Owner' | 'Viewer') {
    if (!token || !window.confirm(`Change ${target.username}'s role to ${role}?`)) return;
    setNotice('');
    try {
      const updated = await updateAdminUserRole(token, target.id, role);
      setUsers((items) => items.map((item) => item.id === updated.id ? updated : item));
      setNotice(`Role updated for ${target.username}.`);
    } catch (reason) {
      setError(axios.isAxiosError(reason) ? String(reason.response?.data?.detail ?? 'Could not update role.') : 'Could not update role.');
    }
  }

  async function setStatus(target: AdminUser, nextStatus: 'ACTIVE' | 'INACTIVE' | 'SUSPENDED') {
    if (!token || !window.confirm(`Set ${target.username}'s account status to ${nextStatus}?`)) return;
    setNotice('');
    try {
      const updated = await updateAdminUserStatus(token, target.id, nextStatus);
      setUsers((items) => items.map((item) => item.id === updated.id ? updated : item));
      setNotice(`Account status updated for ${target.username}.`);
    } catch (reason) {
      setError(axios.isAxiosError(reason) ? String(reason.response?.data?.detail ?? 'Could not update account.') : 'Could not update account.');
    }
  }

  return <section>
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div><h1 className="text-2xl font-bold sm:text-3xl">{labels[mode]}</h1><p className="mt-2 text-gray-600">Account information and administrator controls.</p></div>
      <button className="rounded border border-gray-300 px-3 py-2 text-sm" onClick={() => void refresh()} disabled={loading}>Refresh</button>
    </div>
    {error && <p className="mt-5 rounded bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}
    {notice && <p className="mt-5 rounded bg-green-50 p-3 text-sm text-green-800" role="status">{notice}</p>}
    {loading ? <p className="mt-6 text-gray-600" role="status">Loading users…</p> : <div className="mt-6 overflow-x-auto rounded-xl border border-gray-200 bg-white">
      <table className="min-w-[900px] w-full text-left text-sm">
        <thead className="bg-gray-50 text-xs uppercase text-gray-600"><tr><th className="px-4 py-3">User</th><th className="px-4 py-3">Email</th><th className="px-4 py-3">Role</th><th className="px-4 py-3">Email verified</th><th className="px-4 py-3">Account</th><th className="px-4 py-3">Registered</th>{mode !== 'all' && <th className="px-4 py-3">Actions</th>}</tr></thead>
        <tbody className="divide-y divide-gray-100">
          {users.map((item) => {
            const protectedUser = item.role === 'Administrator' || item.id === currentUser?.id;
            return <tr key={item.id}>
              <td className="px-4 py-3"><span className="font-medium">{item.full_name}</span><span className="block text-gray-500">@{item.username} · ID {item.id}</span></td>
              <td className="px-4 py-3">{item.email}{item.phone_number && <span className="block text-gray-500">{item.phone_number}</span>}</td>
              <td className="px-4 py-3">{item.role}</td>
              <td className="px-4 py-3">{item.email_verified ? 'Verified' : 'Unverified'}</td>
              <td className="px-4 py-3">{item.account_status}</td>
              <td className="px-4 py-3">{new Date(item.registration_date).toLocaleDateString()}</td>
              {mode !== 'all' && <td className="px-4 py-3">
                {mode === 'roles' ? <select className="rounded border border-gray-300 px-2 py-1" aria-label={`Role for ${item.username}`} value={item.role === 'Administrator' ? 'Administrator' : item.role} disabled={protectedUser} onChange={(event) => void setRole(item, event.target.value as 'Owner' | 'Viewer')}>
                  {item.role === 'Administrator' && <option value="Administrator">Administrator</option>}
                  <option value="Owner">Owner</option><option value="Viewer">Viewer</option>
                </select> : <select className="rounded border border-gray-300 px-2 py-1" aria-label={`Account status for ${item.username}`} value={item.account_status} disabled={protectedUser} onChange={(event) => void setStatus(item, event.target.value as 'ACTIVE' | 'INACTIVE' | 'SUSPENDED')}>
                  {item.account_status === 'PENDING' || item.account_status === 'REJECTED' ? <option value={item.account_status}>{item.account_status}</option> : null}
                  <option value="ACTIVE">ACTIVE</option><option value="INACTIVE">INACTIVE</option><option value="SUSPENDED">SUSPENDED</option>
                </select>}
              </td>}
            </tr>;
          })}
          {!users.length && <tr><td className="px-4 py-8 text-center text-gray-500" colSpan={mode === 'all' ? 6 : 7}>No users found.</td></tr>}
        </tbody>
      </table>
    </div>}
  </section>;
}
