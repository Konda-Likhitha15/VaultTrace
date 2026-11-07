import { useEffect, useState } from 'react';
import axios from 'axios';
import { useAppContext } from '../context/AppContext';
import { approveAdminApplication, getAdminApplications, rejectAdminApplication } from '../services/api';
import type { AdminApplication } from '../types';

export function AdminApplicationsPage() {
  const { token } = useAppContext();
  const [applications, setApplications] = useState<AdminApplication[]>([]);
  const [roles, setRoles] = useState<Record<number, 'Owner' | 'Viewer'>>({});
  const [reasons, setReasons] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('PENDING');

  async function refresh() {
    if (!token) return;
    setLoading(true);
    try {
      setApplications(await getAdminApplications(token));
      setError('');
    } catch (reason) {
      setError(axios.isAxiosError(reason) ? String(reason.response?.data?.detail ?? 'Could not load applications.') : 'Could not load applications.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, [token]);

  const visibleApplications = applications.filter((application) => {
    const query = search.trim().toLowerCase();
    const matchesSearch = !query || [application.full_name, application.username, application.email].some((value) => value.toLowerCase().includes(query));
    return matchesSearch && (!statusFilter || application.approval_status === statusFilter);
  });

  async function approve(application: AdminApplication) {
    if (!token || !window.confirm(`Approve ${application.full_name} as ${roles[application.id] ?? 'Viewer'}?`)) return;
    setBusyId(application.id);
    setError('');
    setNotice('');
    try {
      const response = await approveAdminApplication(token, application.id, roles[application.id] ?? 'Viewer');
      setNotice(response.notification_sent === false ? `${response.message} The decision was saved, but the notification email could not be sent.` : response.message);
      await refresh();
    } catch (reason) {
      setError(axios.isAxiosError(reason) ? String(reason.response?.data?.detail ?? 'Could not approve application.') : 'Could not approve application.');
    } finally {
      setBusyId(null);
    }
  }

  async function reject(application: AdminApplication) {
    const reason = reasons[application.id]?.trim() ?? '';
    if (!token || !reason) {
      setError('Enter a rejection reason before rejecting an application.');
      return;
    }
    if (!window.confirm(`Reject the application from ${application.full_name}?`)) return;
    setBusyId(application.id);
    setError('');
    setNotice('');
    try {
      const response = await rejectAdminApplication(token, application.id, reason);
      setNotice(response.notification_sent === false ? `${response.message} The decision was saved, but the notification email could not be sent.` : response.message);
      await refresh();
    } catch (requestError) {
      setError(axios.isAxiosError(requestError) ? String(requestError.response?.data?.detail ?? 'Could not reject application.') : 'Could not reject application.');
    } finally {
      setBusyId(null);
    }
  }

  return <section>
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div><h1 className="text-2xl font-bold sm:text-3xl">Signup applications</h1><p className="mt-2 text-gray-600">Review verified email submissions awaiting a decision.</p></div>
      <button className="rounded border border-gray-300 px-3 py-2 text-sm" disabled={loading} onClick={() => void refresh()}>Refresh</button>
    </div>
    {error && <p className="mt-5 rounded bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}
    {notice && <p className="mt-5 rounded bg-green-50 p-3 text-sm text-green-800" role="status">{notice}</p>}
    {!loading && <div className="mt-5 grid gap-3 rounded-xl border bg-white p-4 sm:grid-cols-2">
      <label className="text-sm font-medium">Find applicant<input className="mt-1 w-full rounded border px-3 py-2" onChange={(event) => setSearch(event.target.value)} placeholder="Name, username, or email" value={search} /></label>
      <label className="text-sm font-medium">Review status<select className="mt-1 w-full rounded border px-3 py-2" onChange={(event) => setStatusFilter(event.target.value)} value={statusFilter}><option value="PENDING">Pending review</option><option value="APPROVED">Approved</option><option value="REJECTED">Rejected</option><option value="">All statuses</option></select></label>
      <p className="text-xs text-gray-600 sm:col-span-2">Showing {visibleApplications.length} of {applications.length} loaded applications.</p>
    </div>}
    {loading ? <p className="mt-6 text-gray-600" role="status">Loading applications…</p> : visibleApplications.length ? <div className="mt-6 space-y-4">
      {visibleApplications.map((application) => <article className="rounded-xl border border-gray-200 bg-white p-5" key={application.id}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h2 className="text-lg font-semibold">{application.full_name}</h2><p className="mt-1 text-sm text-gray-600">@{application.username} · {application.email}</p><p className="mt-1 text-sm text-gray-500">Submitted {new Date(application.submitted_at).toLocaleString()} · Email {application.email_verified ? 'verified' : 'unverified'}</p></div>
          <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800">{application.approval_status}</span>
        </div>
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer font-medium text-indigo-700">View registration details</summary>
          <dl className="mt-3 grid gap-2 sm:grid-cols-2"><div><dt className="text-gray-500">User ID</dt><dd>{application.user_id}</dd></div><div><dt className="text-gray-500">Phone</dt><dd>{application.phone_number || 'Not provided'}</dd></div><div><dt className="text-gray-500">Reviewed by</dt><dd>{application.reviewed_by_id ?? 'Not reviewed'}</dd></div><div><dt className="text-gray-500">Assigned role</dt><dd>{application.assigned_role ?? 'Not assigned'}</dd></div></dl>
        </details>
        {application.approval_status === 'PENDING' && <div className="mt-5 grid gap-3 border-t border-gray-100 pt-4 sm:grid-cols-[160px_1fr_auto_auto]">
          <label className="text-sm font-medium">Assign role
            <select className="mt-1 w-full rounded border border-gray-300 px-2 py-2" value={roles[application.id] ?? 'Viewer'} onChange={(event) => setRoles((items) => ({ ...items, [application.id]: event.target.value as 'Owner' | 'Viewer' }))}>
              <option value="Owner">Owner</option><option value="Viewer">Viewer</option>
            </select>
          </label>
          <label className="text-sm font-medium">Rejection reason
            <textarea className="mt-1 min-h-10 w-full rounded border border-gray-300 px-3 py-2" maxLength={1000} value={reasons[application.id] ?? ''} onChange={(event) => setReasons((items) => ({ ...items, [application.id]: event.target.value }))} />
          </label>
          <button className="self-end rounded bg-indigo-700 px-4 py-2 font-medium text-white disabled:opacity-60" disabled={busyId === application.id || !application.email_verified} onClick={() => void approve(application)}>{busyId === application.id ? 'Saving…' : 'Approve'}</button>
          <button className="self-end rounded border border-red-300 px-4 py-2 font-medium text-red-800 disabled:opacity-60" disabled={busyId === application.id || !reasons[application.id]?.trim()} onClick={() => void reject(application)}>Reject</button>
        </div>}
      </article>)}
    </div> : <p className="mt-6 rounded-xl border border-dashed border-gray-300 p-8 text-center text-gray-600">{applications.length ? 'No applications match these filters.' : 'No applications to review.'}</p>}
  </section>;
}
