import { useEffect, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { apiErrorMessage, getAdminOrganizations, getAdminStorageDetail, getAdminStorageUsers } from '../services/api';
import { useAppContext } from '../context/AppContext';
import type { AdminAnalyticsBreakdown, AdminStorageDetail, AdminStoragePage as StoragePageData, Organization } from '../types';

const PAGE_SIZE = 25;
const colors = ['#4f46e5', '#0f766e', '#d97706', '#be123c', '#7c3aed', '#0284c7'];

function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(2)} GB`;
}

function TypeDonut({ items }: { items: AdminAnalyticsBreakdown[] }) {
  const total = items.reduce((sum, item) => sum + item.count, 0);
  if (!total) return <div className="flex min-h-36 items-center justify-center rounded-lg bg-gray-50 p-5 text-center text-sm text-gray-500">No stored documents.</div>;
  let offset = 0;
  const segments = items.slice(0, 8).map((item, index) => {
    const share = item.count / total * 100;
    const segment = <circle key={item.name} cx="58" cy="58" fill="none" r="40" stroke={colors[index % colors.length]} strokeDasharray={`${share} ${100 - share}`} strokeDashoffset={-offset} pathLength="100" strokeWidth="16"><title>{item.name}: {item.count} documents</title></circle>;
    offset += share;
    return segment;
  });
  return <div className="flex flex-wrap items-center gap-4"><svg aria-label="Customer document counts by file type" className="h-32 w-32 shrink-0 -rotate-90" role="img" viewBox="0 0 116 116"><circle cx="58" cy="58" fill="none" r="40" stroke="#e5e7eb" strokeWidth="16" />{segments}</svg><ul className="min-w-36 flex-1 space-y-2 text-xs">{items.slice(0, 8).map((item, index) => <li className="flex justify-between gap-3" key={item.name}><span className="flex items-center gap-2"><i aria-hidden="true" className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: colors[index % colors.length] }} />{item.name}</span><strong>{item.count}</strong></li>)}</ul></div>;
}

export function AdminStoragePage() {
  const { token } = useAppContext();
  const [page, setPage] = useState<StoragePageData | null>(null);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [organizationId, setOrganizationId] = useState<number | undefined>();
  const [sortBy, setSortBy] = useState<'storage_bytes' | 'document_count'>('storage_bytes');
  const [offset, setOffset] = useState(0);
  const [reload, setReload] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token) return;
    let active = true;
    void getAdminOrganizations(token).then((result) => { if (active) setOrganizations(result); }).catch(() => { if (active) setOrganizations([]); });
    return () => { active = false; };
  }, [token]);

  useEffect(() => {
    if (!token) return;
    let active = true;
    setLoading(true); setError('');
    void getAdminStorageUsers(token, { search: search || undefined, organization_id: organizationId, sort_by: sortBy, limit: PAGE_SIZE, offset })
      .then((data) => { if (active) setPage(data); })
      .catch(async (reason: unknown) => { if (active) setError(await apiErrorMessage(reason, 'Storage report could not be loaded.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, search, organizationId, sortBy, offset, reload]);

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setOffset(0); setSearch(searchInput.trim());
  }

  return <section>
    <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">Administration</p><h1 className="mt-1 text-3xl font-bold">Storage management</h1><p className="mt-2 max-w-3xl text-gray-600">Recorded bytes include current files and retained earlier versions. Soft-deleted files remain in storage until permanently removed.</p></div><Link className="rounded border bg-white px-3 py-2 text-sm" to="/admin/dashboard">Analytics overview</Link></header>
    <div className="mt-5 rounded-lg bg-amber-50 p-4 text-sm text-amber-900">Usage is calculated from file-size metadata in the database; it is not an independent provider billing measurement. No per-user quota is configured, so remaining capacity and quota percentages are unavailable.</div>
    <form className="mt-5 grid gap-3 rounded-xl border bg-white p-4 sm:grid-cols-2 xl:grid-cols-4" onSubmit={submitSearch}>
      <label className="text-sm font-medium">Search user<input className="mt-1 w-full rounded border px-3 py-2" maxLength={160} onChange={(event) => setSearchInput(event.target.value)} placeholder="Username, name, or email" value={searchInput} /></label>
      <label className="text-sm font-medium">Organization<select className="mt-1 w-full rounded border px-3 py-2" onChange={(event) => { setOrganizationId(event.target.value ? Number(event.target.value) : undefined); setOffset(0); }} value={organizationId ?? ''}><option value="">All organizations</option>{organizations.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label className="text-sm font-medium">Sort by<select className="mt-1 w-full rounded border px-3 py-2" onChange={(event) => { setSortBy(event.target.value as typeof sortBy); setOffset(0); }} value={sortBy}><option value="storage_bytes">Storage consumed</option><option value="document_count">Document count</option></select></label>
      <div className="flex items-end gap-2"><button className="rounded bg-indigo-700 px-4 py-2 text-sm font-semibold text-white" type="submit">Search</button><button className="rounded border px-4 py-2 text-sm" disabled={loading} onClick={() => setReload((value) => value + 1)} type="button">Refresh</button></div>
    </form>
    {error && <p className="mt-4 rounded bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}
    {loading && <p className="mt-4 text-sm text-gray-600" role="status">Loading customer storage…</p>}
    <div className="mt-5 overflow-x-auto rounded-xl border bg-white">
      <table className="min-w-[1100px] w-full text-left text-sm"><thead className="bg-gray-50 text-xs uppercase text-gray-600"><tr><th className="px-4 py-3">Customer</th><th className="px-4 py-3">Organization</th><th className="px-4 py-3">Documents</th><th className="px-4 py-3">Recorded storage</th><th className="px-4 py-3">Quota usage</th><th className="px-4 py-3">Largest file</th><th className="px-4 py-3">Last upload</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Details</th></tr></thead>
        <tbody className="divide-y">{page?.items.map((item) => <tr key={item.user_id}><td className="px-4 py-3"><strong>@{item.username}</strong><span className="block text-gray-500">{item.email} · ID {item.user_id}</span></td><td className="px-4 py-3">{item.organization_name ?? 'Unassigned'}</td><td className="px-4 py-3">{item.document_count}</td><td className="px-4 py-3 font-medium">{formatBytes(item.storage_bytes)}</td><td className="px-4 py-3">{item.quota_bytes ? `${(item.storage_bytes / item.quota_bytes * 100).toFixed(1)}%` : 'Not configured'}</td><td className="px-4 py-3">{formatBytes(item.largest_file_bytes)}</td><td className="px-4 py-3">{item.last_upload_at ? new Date(item.last_upload_at).toLocaleString() : '—'}</td><td className="px-4 py-3">{item.account_status}</td><td className="px-4 py-3"><Link className="font-medium text-indigo-700 hover:underline" to={`/admin/storage/users/${item.user_id}`}>View storage</Link></td></tr>)}
          {!loading && !page?.items.length && <tr><td className="px-4 py-8 text-center text-gray-500" colSpan={9}>No customers match these filters.</td></tr>}</tbody>
      </table>
    </div>
    <div className="mt-4 flex items-center justify-between"><span className="text-sm text-gray-600">{page ? `Showing ${page.total ? offset + 1 : 0}–${Math.min(offset + PAGE_SIZE, page.total)} of ${page.total}` : ''}</span><div className="flex gap-2"><button className="rounded border px-3 py-2 text-sm disabled:opacity-50" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} type="button">Previous</button><button className="rounded border px-3 py-2 text-sm disabled:opacity-50" disabled={!page || offset + PAGE_SIZE >= page.total || loading} onClick={() => setOffset(offset + PAGE_SIZE)} type="button">Next</button></div></div>
  </section>;
}

export function AdminStorageUserPage() {
  const { userId } = useParams();
  const { token } = useAppContext();
  const [data, setData] = useState<AdminStorageDetail | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const id = Number(userId);

  useEffect(() => {
    if (!token || !Number.isInteger(id) || id < 1) return;
    let active = true;
    setLoading(true); setError('');
    void getAdminStorageDetail(token, id, offset, PAGE_SIZE).then((result) => { if (active) setData(result); })
      .catch(async (reason: unknown) => { if (active) setError(await apiErrorMessage(reason, 'Customer storage details could not be loaded.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, id, offset]);

  return <section>
    <Link className="text-sm text-indigo-700 hover:underline" to="/admin/storage">← Back to storage management</Link>
    {loading && <p className="mt-5 text-sm text-gray-600" role="status">Loading customer details…</p>}
    {error && <p className="mt-5 rounded bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}
    {data && <>
      <header className="mt-5"><p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">Customer storage detail</p><h1 className="mt-1 text-3xl font-bold">{data.user.full_name}</h1><p className="mt-2 text-gray-600">@{data.user.username} · {data.user.email}</p></header>
      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[['Documents', data.user.document_count], ['Recorded storage', formatBytes(data.user.storage_bytes)], ['Largest file', formatBytes(data.user.largest_file_bytes)], ['Account status', data.user.account_status]].map(([label, value]) => <article className="rounded-xl border bg-white p-4" key={String(label)}><p className="text-sm text-gray-500">{label}</p><p className="mt-2 text-xl font-bold">{value}</p></article>)}</div>
      <div className="mt-5 grid gap-5 xl:grid-cols-2"><article className="rounded-xl border bg-white p-5"><h2 className="font-semibold">Customer information</h2><dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2"><div><dt className="text-gray-500">User ID</dt><dd>{data.user.user_id}</dd></div><div><dt className="text-gray-500">Organization</dt><dd>{data.user.organization_name ?? 'Unassigned'}</dd></div><div><dt className="text-gray-500">Last upload</dt><dd>{data.user.last_upload_at ? new Date(data.user.last_upload_at).toLocaleString() : 'No uploads recorded'}</dd></div><div><dt className="text-gray-500">Quota</dt><dd>Not configured</dd></div></dl></article><article className="rounded-xl border bg-white p-5"><h2 className="font-semibold">Documents by file type</h2><p className="mb-4 mt-1 text-xs text-gray-500">Current document format counts.</p><TypeDonut items={data.file_types} /></article></div>
      <article className="mt-5 rounded-xl border bg-white p-5"><h2 className="font-semibold">Customer documents</h2><p className="mt-1 text-xs text-gray-500">Current file size is shown separately from all retained bytes for that document.</p><div className="mt-4 overflow-x-auto"><table className="min-w-[780px] w-full text-left text-sm"><thead className="bg-gray-50 text-xs uppercase text-gray-600"><tr><th className="px-3 py-2">Document</th><th className="px-3 py-2">Type</th><th className="px-3 py-2">Current file</th><th className="px-3 py-2">Total retained</th><th className="px-3 py-2">Versions</th><th className="px-3 py-2">Last upload</th><th className="px-3 py-2">State</th></tr></thead><tbody className="divide-y">{data.documents.map((item) => <tr key={item.document_id}><td className="px-3 py-3"><span className="font-medium">{item.document_name}</span><span className="block text-xs text-gray-500">{item.document_id}</span></td><td className="px-3 py-3">{item.file_extension.toUpperCase()}</td><td className="px-3 py-3">{formatBytes(item.current_file_bytes)}</td><td className="px-3 py-3 font-medium">{formatBytes(item.total_stored_bytes)}</td><td className="px-3 py-3">{item.version_count}</td><td className="px-3 py-3">{new Date(item.uploaded_at).toLocaleString()}</td><td className="px-3 py-3">{item.deleted_at ? 'Soft deleted; bytes retained' : 'Active'}</td></tr>)}{!data.documents.length && <tr><td className="px-3 py-8 text-center text-gray-500" colSpan={7}>No documents recorded for this user.</td></tr>}</tbody></table></div>
        <div className="mt-4 flex items-center justify-between text-sm"><span>{data.document_total ? `Showing ${offset + 1}–${Math.min(offset + PAGE_SIZE, data.document_total)} of ${data.document_total}` : 'No documents'}</span><div className="flex gap-2"><button className="rounded border px-3 py-2 disabled:opacity-50" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} type="button">Previous</button><button className="rounded border px-3 py-2 disabled:opacity-50" disabled={offset + PAGE_SIZE >= data.document_total || loading} onClick={() => setOffset(offset + PAGE_SIZE)} type="button">Next</button></div></div>
      </article>
      <article className="mt-5 rounded-xl border bg-white p-5"><h2 className="font-semibold">Recent storage activity</h2>{data.recent_activity.length ? <ul className="mt-3 divide-y">{data.recent_activity.map((item, index) => <li className="flex flex-wrap justify-between gap-2 py-3 text-sm" key={`${item.created_at}-${index}`}><span>{item.action.replaceAll('_', ' ').toLowerCase()} · {item.actor_username} · {item.result.toLowerCase()}</span><time className="text-gray-500">{new Date(item.created_at).toLocaleString()}</time></li>)}</ul> : <p className="mt-3 rounded-lg bg-gray-50 p-4 text-sm text-gray-500">No upload activity is available.</p>}</article>
      <p className="mt-5 rounded-lg bg-amber-50 p-4 text-sm text-amber-900">{data.historical_storage_note} Current storage is database-recorded metadata; object-store availability and billing bytes are not independently verified here.</p>
    </>}
  </section>;
}
