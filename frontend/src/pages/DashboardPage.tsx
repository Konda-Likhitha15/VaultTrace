import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAppContext } from '../context/AppContext';
import { apiErrorMessage, getDocumentActivity, getDocuments, getMyStorageUsage, getSharedByMe, getSharedWithMe } from '../services/api';
import type { DocumentActivity, DocumentMetadata, SharedByMe, SharedDocument } from '../types';

const palette = ['#4f46e5', '#0f766e', '#d97706', '#be123c', '#7c3aed', '#0284c7'];
const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
type NamedActivity = DocumentActivity & { document_name: string };

function bytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function UploadChart({ documents }: { documents: DocumentMetadata[] }) {
  const points = useMemo(() => {
    const dates = Array.from({ length: 6 }, (_, index) => {
      const date = new Date(); date.setDate(1); date.setMonth(date.getMonth() - (5 - index));
      return { key: `${date.getFullYear()}-${date.getMonth()}`, label: monthNames[date.getMonth()], count: 0 };
    });
    for (const document of documents) {
      const date = new Date(document.created_at);
      const point = dates.find((item) => item.key === `${date.getFullYear()}-${date.getMonth()}`);
      if (point) point.count += 1;
    }
    return dates;
  }, [documents]);
  const max = Math.max(1, ...points.map((point) => point.count));
  const coordinates = points.map((point, index) => `${36 + index * 64},${116 - point.count / max * 82}`).join(' ');
  if (!documents.length) return <EmptyChart text="Uploads will appear here when you add documents." />;
  return <div>
    <svg aria-label="Document uploads over the last six months" className="h-44 w-full overflow-visible" role="img" viewBox="0 0 390 145">
      <path d="M32 118H370M32 77H370M32 36H370" fill="none" stroke="#e5e7eb" />
      <polyline fill="none" points={coordinates} stroke="#4f46e5" strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" />
      {points.map((point, index) => <g key={point.key}><circle cx={36 + index * 64} cy={116 - point.count / max * 82} r="4" fill="#4f46e5" /><text fill="#6b7280" fontSize="10" textAnchor="middle" x={36 + index * 64} y="138">{point.label}</text></g>)}
    </svg>
    <div className="sr-only">{points.map((point) => `${point.label}: ${point.count}`).join(', ')}</div>
  </div>;
}

function TypeChart({ documents }: { documents: DocumentMetadata[] }) {
  const groups = useMemo(() => {
    const counts = new Map<string, number>();
    documents.forEach((item) => { const type = item.file_extension.toUpperCase() || 'OTHER'; counts.set(type, (counts.get(type) ?? 0) + 1); });
    const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]);
    if (sorted.length <= 6) return sorted;
    const visible = sorted.slice(0, 5);
    visible.push(['OTHER', sorted.slice(5).reduce((sum, item) => sum + item[1], 0)]);
    return visible;
  }, [documents]);
  const total = groups.reduce((sum, item) => sum + item[1], 0);
  if (!total) return <EmptyChart text="File-type breakdown appears after your first upload." />;
  let offset = 0;
  const circles = groups.map(([label, count], index) => {
    const dash = (count / total) * 100;
    const segment = <circle key={label} cx="60" cy="60" fill="none" r="42" stroke={palette[index % palette.length]} strokeDasharray={`${dash} ${100 - dash}`} strokeDashoffset={-offset} pathLength="100" strokeWidth="17" />;
    offset += dash;
    return segment;
  });
  return <div className="flex flex-wrap items-center gap-5">
    <svg aria-label="Documents by file type" className="h-32 w-32 -rotate-90" role="img" viewBox="0 0 120 120"><circle cx="60" cy="60" fill="none" r="42" stroke="#e5e7eb" strokeWidth="17" />{circles}</svg>
    <ul className="min-w-32 flex-1 space-y-2 text-sm">{groups.map(([label, count], index) => <li className="flex items-center justify-between gap-3" key={label}><span className="flex items-center gap-2"><i aria-hidden="true" className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: palette[index % palette.length] }} />{label}</span><span className="font-medium">{count}</span></li>)}</ul>
  </div>;
}

function ShareChart({ sharedByMe, sharedWithMe }: { sharedByMe: number; sharedWithMe: number }) {
  const max = Math.max(sharedByMe, sharedWithMe, 1);
  if (!sharedByMe && !sharedWithMe) return <EmptyChart text="Sharing activity will appear when a document is shared." />;
  return <div className="space-y-5 pt-3">
    {[['Shared by me', sharedByMe, '#4f46e5'], ['Shared with me', sharedWithMe, '#0f766e']].map(([label, count, color]) => <div key={String(label)}><div className="mb-1 flex justify-between text-sm"><span>{label}</span><span className="font-semibold">{count}</span></div><div className="h-3 overflow-hidden rounded-full bg-gray-100"><div aria-label={`${label}: ${count}`} className="h-full rounded-full" role="img" style={{ width: `${Number(count) / max * 100}%`, backgroundColor: String(color) }} /></div></div>)}
  </div>;
}

function EmptyChart({ text }: { text: string }) {
  return <div className="flex min-h-36 items-center justify-center rounded-lg bg-gray-50 px-5 text-center text-sm text-gray-500">{text}</div>;
}

function actionName(action: string): string {
  return action.replaceAll('_', ' ').toLowerCase().replace(/^./, (char) => char.toUpperCase());
}

export function DashboardPage() {
  const { user, token } = useAppContext();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [documents, setDocuments] = useState<DocumentMetadata[]>([]);
  const [storageUsed, setStorageUsed] = useState(0);
  const [sharedWithMe, setSharedWithMe] = useState<SharedDocument[]>([]);
  const [sharedByMe, setSharedByMe] = useState<SharedByMe[]>([]);
  const [activity, setActivity] = useState<NamedActivity[]>([]);
  const isOwner = user?.role === 'Owner';

  useEffect(() => {
    if (!token) return;
    let active = true;
    async function load() {
      setLoading(true); setError('');
      try {
        const [incoming, outgoing, usage] = await Promise.all([getSharedWithMe(token!), getSharedByMe(token!), getMyStorageUsage(token!)]);
        const owned: DocumentMetadata[] = [];
        let offset = 0;
        let page: DocumentMetadata[];
        do {
          page = await getDocuments(token!, { limit: 100, offset, sort_by: 'created_at', sort_order: 'desc' });
          owned.push(...page);
          offset += page.length;
        } while (page.length === 100);
        if (!active) return;
        setDocuments(owned); setSharedWithMe(incoming); setSharedByMe(outgoing); setStorageUsed(usage.total_stored_bytes);
        const activityDocuments = [...owned, ...incoming.map((item) => item.document)]
          .filter((item, index, all) => all.findIndex((candidate) => candidate.id === item.id) === index)
          .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
          .slice(0, 8);
        const recent = await Promise.allSettled(activityDocuments.map(async (item) => ({ document_name: item.document_name, events: await getDocumentActivity(token!, item.id) })));
        if (active) setActivity(recent.flatMap((result) => result.status === 'fulfilled' ? result.value.events.map((event) => ({ ...event, document_name: result.value.document_name })) : []).sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).slice(0, 8));
      } catch (reason) {
        if (active) setError(await apiErrorMessage(reason, 'Dashboard data could not be loaded.'));
      } finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, [token, reload]);

  const recentDocuments = documents.slice(0, 5);
  const recentShares = sharedByMe.filter((item) => !item.revoked_at).slice(0, 5);
  const currentMonth = new Date();
  const uploadedThisMonth = documents.filter((document) => {
    const created = new Date(document.created_at);
    return created.getFullYear() === currentMonth.getFullYear() && created.getMonth() === currentMonth.getMonth();
  }).length;
  const recentlyAccessed = activity.filter((item) => ['DOCUMENT_DOWNLOADED', 'DOCUMENT_PREVIEWED'].includes(item.action)).slice(0, 5);

  return <main className="mx-auto w-full max-w-7xl space-y-7">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">VaultTrace</p><h1 className="mt-1 text-3xl font-bold">Dashboard</h1><p className="mt-2 text-gray-600">A live view of your document workspace.</p></div><div className="flex gap-2"><button className="rounded border bg-white px-3 py-2 text-sm font-medium disabled:opacity-50" disabled={loading} onClick={() => setReload((value) => value + 1)} type="button">{loading ? 'Refreshing…' : 'Refresh'}</button><Link className="rounded border bg-white px-3 py-2 text-sm font-medium" to="/documents">Browse documents</Link>{isOwner && <Link className="rounded bg-indigo-700 px-3 py-2 text-sm font-semibold text-white" to="/documents/upload">Upload document</Link>}</div></header>
    {user && <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-label="Workspace summary">
      {[["Total documents", documents.length, "Active documents owned by you"], ["Uploaded this month", uploadedThisMonth, "New documents"], ["Shared with me", sharedWithMe.length, "Active access grants"], ["Shared by me", sharedByMe.filter((item) => !item.revoked_at).length, "Active grants"], ["Storage used", bytes(storageUsed), "Current and retained-version metadata"], ["Recent activity", activity.length, "From recent accessible documents"]].map(([label, value, note]) => <article className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm" key={String(label)}><p className="text-sm text-gray-500">{label}</p><p aria-label={loading ? `Loading ${label}` : undefined} className="mt-2 text-2xl font-bold">{loading ? '—' : value}</p><p className="mt-1 text-xs text-gray-500">{note}</p></article>)}
    </section>}
    {loading && <p className="text-sm text-gray-600" role="status">Loading your workspace…</p>}
    {error && <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-red-50 p-4 text-sm text-red-800" role="alert"><span>{error}</span><button className="rounded border border-red-300 px-3 py-1.5" disabled={loading} onClick={() => setReload((value) => value + 1)} type="button">Try again</button></div>}
    <section className="grid gap-5 xl:grid-cols-2" aria-label="Document analytics">
      <article className="rounded-xl border bg-white p-5 shadow-sm"><h2 className="font-semibold">Uploads over time</h2><p className="mt-1 text-sm text-gray-500">Monthly uploads from your owned document records.</p><div className="mt-3">{loading ? <p className="py-12 text-center text-sm text-gray-500" role="status">Loading chart data…</p> : <UploadChart documents={documents} />}</div></article>
      <article className="rounded-xl border bg-white p-5 shadow-sm"><h2 className="font-semibold">Documents by file type</h2><p className="mt-1 text-sm text-gray-500">Based on your current owned documents.</p><div className="mt-4">{loading ? <p className="py-12 text-center text-sm text-gray-500" role="status">Loading chart data…</p> : <TypeChart documents={documents} />}</div></article>
      <article className="rounded-xl border bg-white p-5 shadow-sm"><h2 className="font-semibold">Storage utilization</h2><p className="mt-1 text-sm text-gray-500">{loading ? 'Loading storage data…' : `Recorded current and retained file bytes total ${bytes(storageUsed)}.`}</p><div className="mt-6 rounded-lg bg-gray-50 p-4 text-sm text-gray-600">{loading ? 'Loading storage data…' : 'A storage quota is not configured for this account, so percentage utilization is unavailable.'}</div></article>
      <article className="rounded-xl border bg-white p-5 shadow-sm"><h2 className="font-semibold">Sharing activity</h2><p className="mt-1 text-sm text-gray-500">Active grants visible to your account.</p>{loading ? <p className="py-12 text-center text-sm text-gray-500" role="status">Loading chart data…</p> : <ShareChart sharedByMe={sharedByMe.filter((item) => !item.revoked_at).length} sharedWithMe={sharedWithMe.length} />}</article>
    </section>
    <section className="grid gap-5 xl:grid-cols-2">
      <article className="rounded-xl border bg-white p-5 shadow-sm"><div className="flex items-center justify-between gap-3"><h2 className="font-semibold">Recent documents</h2><Link className="text-sm text-indigo-700 hover:underline" to="/documents">View all</Link></div>{loading ? <p className="mt-6 text-sm text-gray-500" role="status">Loading documents…</p> : recentDocuments.length ? <ul className="mt-3 divide-y">{recentDocuments.map((item) => <li className="flex items-center justify-between gap-3 py-3" key={item.id}><div className="min-w-0"><p className="truncate font-medium">{item.document_name}</p><p className="text-xs text-gray-500">{item.file_extension.toUpperCase()} · {bytes(item.file_size)} · {new Date(item.created_at).toLocaleDateString()}</p></div><span className="rounded bg-gray-100 px-2 py-1 text-xs">v{item.current_version}</span></li>)}</ul> : <EmptyChart text="Your uploaded documents will appear here." />}</article>
      <article className="rounded-xl border bg-white p-5 shadow-sm"><h2 className="font-semibold">Recently accessed</h2>{loading ? <p className="mt-6 text-sm text-gray-500" role="status">Loading access history…</p> : recentlyAccessed.length ? <ul className="mt-3 divide-y">{recentlyAccessed.map((item) => <li className="py-3" key={item.id}><p className="truncate font-medium">{item.document_name}</p><p className="text-xs text-gray-500">{actionName(item.action)} · {new Date(item.created_at).toLocaleString()}</p></li>)}</ul> : <div className="mt-3"><EmptyChart text="Document previews and downloads will appear here." /></div>}</article>
      <article className="rounded-xl border bg-white p-5 shadow-sm"><h2 className="font-semibold">Recent activity</h2>{loading ? <p className="mt-6 text-sm text-gray-500" role="status">Loading recent activity…</p> : activity.length ? <ul className="mt-3 divide-y">{activity.slice(0, 6).map((item) => <li className="py-3" key={item.id}><p className="font-medium">{actionName(item.action)} · {item.document_name}</p><p className="text-xs text-gray-500">{item.actor_username} · {new Date(item.created_at).toLocaleString()}</p></li>)}</ul> : <div className="mt-3"><EmptyChart text="Recent document activity will appear here when available." /></div>}</article>
      <article className="rounded-xl border bg-white p-5 shadow-sm"><h2 className="font-semibold">Recently shared</h2>{recentShares.length ? <ul className="mt-3 divide-y">{recentShares.map((item) => <li className="flex justify-between gap-3 py-3" key={item.permission_id}><span className="truncate font-medium">{item.document_name}</span><span className="shrink-0 text-sm text-gray-500">with @{item.recipient_username}</span></li>)}</ul> : <div className="mt-3"><EmptyChart text="Documents you share with others will appear here." /></div>}</article>
      <article className="rounded-xl border bg-white p-5 shadow-sm"><h2 className="font-semibold">Quick actions</h2><div className="mt-4 grid gap-3 sm:grid-cols-2"><Link className="rounded-lg border p-4 font-medium hover:border-indigo-400" to={isOwner ? '/documents/upload' : '/documents'}>{isOwner ? 'Upload a document' : 'Browse documents'}<span className="mt-1 block text-xs font-normal text-gray-500">Open your workspace</span></Link><Link className="rounded-lg border p-4 font-medium hover:border-indigo-400" to="/documents/shared">Shared with me<span className="mt-1 block text-xs font-normal text-gray-500">View documents others granted you</span></Link><Link className="rounded-lg border p-4 font-medium hover:border-indigo-400" to="/profile">My profile<span className="mt-1 block text-xs font-normal text-gray-500">Manage personal information and security</span></Link></div></article>
    </section>
  </main>;
}
