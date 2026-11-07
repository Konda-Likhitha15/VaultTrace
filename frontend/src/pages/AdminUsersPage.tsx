import { useEffect, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { useAppContext } from '../context/AppContext';
import { assignUserOrganization, createAdminOrganization, getAdminOrganizations, getAdminUsers, updateAdminUserRole, updateAdminUserStatus } from '../services/api';
import type { AdminUser, Organization } from '../types';

type ManagementMode = 'all' | 'roles' | 'accounts';
const labels: Record<ManagementMode, string> = { all: 'All users', roles: 'Role management', accounts: 'Account management' };

function requestError(reason: unknown, fallback: string): string {
  if (!axios.isAxiosError(reason)) return reason instanceof Error ? reason.message : fallback;
  const detail: unknown = reason.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.flatMap((entry: unknown) => typeof entry === 'object' && entry !== null && 'msg' in entry && typeof entry.msg === 'string' ? [entry.msg] : []);
    if (messages.length) return messages.join(' ');
  }
  if (!reason.response) return 'Could not reach the VaultTrace API. Check that the backend and database are running.';
  return `The request failed (HTTP ${reason.response.status}). Check the backend logs for details.`;
}

export function AdminUsersPage({ mode }: { mode: ManagementMode }) {
  const { token, user: currentUser } = useAppContext();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [pendingUserId, setPendingUserId] = useState<number | null>(null);
  const [filterText, setFilterText] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [organizationName, setOrganizationName] = useState('');

  async function refresh() {
    if (!token) return;
    setLoading(true);
    try {
      const [nextUsers, nextOrganizations] = await Promise.all([getAdminUsers(token), getAdminOrganizations(token)]);
      setUsers(nextUsers);
      setOrganizations(nextOrganizations);
      setError('');
    } catch (reason) {
      setError(requestError(reason, 'Could not load users.'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, [token]);

  async function setRole(target: AdminUser, role: 'Owner' | 'Viewer') {
    if (!token || pendingUserId !== null || !window.confirm(`Change ${target.username}'s role to ${role}?`)) return;
    setNotice(''); setError(''); setPendingUserId(target.id);
    try {
      const updated = await updateAdminUserRole(token, target.id, role);
      setUsers((items) => items.map((item) => item.id === updated.id ? updated : item));
      setNotice(`Role updated for ${target.username}.`);
      await refresh();
    } catch (reason) {
      setError(requestError(reason, 'Could not update role.'));
    } finally { setPendingUserId(null); }
  }

  async function setStatus(target: AdminUser, nextStatus: 'ACTIVE' | 'INACTIVE' | 'SUSPENDED') {
    if (!token || pendingUserId !== null || !window.confirm(`Set ${target.username}'s account status to ${nextStatus}?`)) return;
    setNotice(''); setError(''); setPendingUserId(target.id);
    try {
      const updated = await updateAdminUserStatus(token, target.id, nextStatus);
      setUsers((items) => items.map((item) => item.id === updated.id ? updated : item));
      setNotice(`Account status updated for ${target.username}.`);
      await refresh();
    } catch (reason) {
      setError(requestError(reason, 'Could not update account.'));
    } finally { setPendingUserId(null); }
  }

  async function setOrganization(target: AdminUser, value: string) {
    if (!token || pendingUserId !== null) return;
    const organizationId = value ? Number(value) : null;
    if (!window.confirm(`${organizationId === null ? 'Remove' : 'Assign'} ${target.username} ${organizationId === null ? 'from their organization' : `to ${organizations.find((item) => item.id === organizationId)?.name}`}?`)) return;
    setPendingUserId(target.id); setError(''); setNotice('');
    try {
      const updated = await assignUserOrganization(token, target.id, organizationId);
      setUsers((items) => items.map((item) => item.id === updated.id ? updated : item));
      setNotice(`Organization membership updated for ${target.username}.`);
      await refresh();
    } catch (reason) { setError(requestError(reason, 'Could not update organization membership.')); }
    finally { setPendingUserId(null); }
  }

  async function addOrganization(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || pendingUserId !== null) return;
    const name = organizationName.trim();
    if (!name || name.length > 120) return;
    setPendingUserId(-1); setError(''); setNotice('');
    try {
      await createAdminOrganization(token, name.trim());
      setNotice(`Organization “${name.trim()}” created.`);
      setOrganizationName('');
      await refresh();
    } catch (reason) { setError(requestError(reason, 'Could not create organization.')); }
    finally { setPendingUserId(null); }
  }

  const visibleUsers = users.filter((item) => {
    const query = filterText.trim().toLowerCase();
    const matchesText = !query || [item.full_name, item.username, item.email, item.organization_id ? String(item.organization_id) : ''].some((value) => value.toLowerCase().includes(query));
    return matchesText && (!roleFilter || item.role === roleFilter) && (!statusFilter || item.account_status === statusFilter);
  });

  return <section>
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div><h1 className="text-2xl font-bold sm:text-3xl">{labels[mode]}</h1><p className="mt-2 text-gray-600">Account information and administrator controls.</p></div>
      <button className="rounded border border-gray-300 px-3 py-2 text-sm" onClick={() => void refresh()} disabled={loading || pendingUserId !== null}>{loading ? 'Refreshing…' : 'Refresh'}</button>
    </div>
    <form className="mt-5 flex flex-wrap items-end gap-3 rounded-xl border bg-white p-4" onSubmit={(event) => void addOrganization(event)}>
      <label className="min-w-60 flex-1 text-sm font-medium">Create organization
        <input className="mt-1 w-full rounded border px-3 py-2" maxLength={120} required value={organizationName} onChange={(event) => setOrganizationName(event.target.value)} placeholder="Organization name" />
      </label>
      <button className="rounded border border-gray-300 px-3 py-2 text-sm disabled:opacity-50" disabled={loading || pendingUserId !== null || !organizationName.trim()} type="submit">{pendingUserId === -1 ? 'Creating…' : 'Create organization'}</button>
    </form>
    {error && <p className="mt-5 rounded bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}
    {notice && <p className="mt-5 rounded bg-green-50 p-3 text-sm text-green-800" role="status">{notice}</p>}
    {!loading && <div className="mt-5 grid gap-3 rounded-xl border bg-white p-4 sm:grid-cols-3">
      <label className="text-sm font-medium sm:col-span-1">Find user<input className="mt-1 w-full rounded border px-3 py-2" onChange={(event) => setFilterText(event.target.value)} placeholder="Name, username, email, organization ID" value={filterText} /></label>
      <label className="text-sm font-medium">Role<select className="mt-1 w-full rounded border px-3 py-2" onChange={(event) => setRoleFilter(event.target.value)} value={roleFilter}><option value="">All roles</option><option value="Administrator">Administrator</option><option value="Owner">Owner</option><option value="Viewer">Viewer</option></select></label>
      <label className="text-sm font-medium">Account status<select className="mt-1 w-full rounded border px-3 py-2" onChange={(event) => setStatusFilter(event.target.value)} value={statusFilter}><option value="">All statuses</option>{Array.from(new Set(users.map((item) => item.account_status))).sort().map((status) => <option key={status}>{status}</option>)}</select></label>
      <p className="text-xs text-gray-600 sm:col-span-3">Showing {visibleUsers.length} of {users.length} loaded accounts. Filtering is performed in this browser.</p>
    </div>}
    {loading ? <p className="mt-6 text-gray-600" role="status">Loading users…</p> : <div className="mt-6 overflow-x-auto rounded-xl border border-gray-200 bg-white">
      <table className="min-w-[900px] w-full text-left text-sm">
        <thead className="bg-gray-50 text-xs uppercase text-gray-600"><tr><th className="px-4 py-3">User</th><th className="px-4 py-3">Email</th><th className="px-4 py-3">Role</th><th className="px-4 py-3">Organization</th><th className="px-4 py-3">Email verified</th><th className="px-4 py-3">Account</th><th className="px-4 py-3">Registered</th>{mode !== 'all' && <th className="px-4 py-3">Actions</th>}</tr></thead>
        <tbody className="divide-y divide-gray-100">
          {visibleUsers.map((item) => {
            const protectedUser = item.role === 'Administrator' || item.id === currentUser?.id;
            return <tr key={item.id}>
              <td className="px-4 py-3"><span className="font-medium">{item.full_name}</span><span className="block text-gray-500">@{item.username} · ID {item.id}</span><Link className="mt-1 inline-block text-xs font-medium text-indigo-700 hover:underline" to={`/admin/storage/users/${item.id}`}>View storage</Link></td>
              <td className="px-4 py-3">{item.email}{item.phone_number && <span className="block text-gray-500">{item.phone_number}</span>}</td>
              <td className="px-4 py-3">{item.role}</td>
              <td className="px-4 py-3"><select aria-label={`Organization for ${item.username}`} className="max-w-48 rounded border border-gray-300 px-2 py-1" value={item.organization_id ?? ''} disabled={pendingUserId !== null} onChange={(event) => void setOrganization(item, event.target.value)}><option value="">Unassigned</option>{organizations.map((organization) => <option key={organization.id} value={organization.id}>{organization.name} ({organization.member_count})</option>)}</select></td>
              <td className="px-4 py-3">{item.email_verified ? 'Verified' : 'Unverified'}</td>
              <td className="px-4 py-3">{item.account_status}</td>
              <td className="px-4 py-3">{new Date(item.registration_date).toLocaleDateString()}</td>
              {mode !== 'all' && <td className="px-4 py-3">
                {mode === 'roles' ? <select className="rounded border border-gray-300 px-2 py-1" aria-label={`Role for ${item.username}`} value={item.role === 'Administrator' ? 'Administrator' : item.role} disabled={protectedUser || pendingUserId !== null} onChange={(event) => void setRole(item, event.target.value as 'Owner' | 'Viewer')}>
                  {item.role === 'Administrator' && <option value="Administrator">Administrator</option>}
                  <option value="Owner">Owner</option><option value="Viewer">Viewer</option>
                </select> : <select className="rounded border border-gray-300 px-2 py-1" aria-label={`Account status for ${item.username}`} value={item.account_status} disabled={protectedUser || pendingUserId !== null} onChange={(event) => void setStatus(item, event.target.value as 'ACTIVE' | 'INACTIVE' | 'SUSPENDED')}>
                  {item.account_status === 'PENDING' || item.account_status === 'REJECTED' ? <option value={item.account_status}>{item.account_status}</option> : null}
                  <option value="ACTIVE">ACTIVE</option><option value="INACTIVE">INACTIVE</option><option value="SUSPENDED">SUSPENDED</option>
                </select>}
                {pendingUserId === item.id && <span className="ml-2 text-xs text-gray-500" role="status">Updating…</span>}
              </td>}
            </tr>;
          })}
          {!visibleUsers.length && <tr><td className="px-4 py-8 text-center text-gray-500" colSpan={mode === 'all' ? 7 : 8}>{users.length ? 'No users match these filters.' : 'No users found.'}</td></tr>}
        </tbody>
      </table>
    </div>}
  </section>;
}
