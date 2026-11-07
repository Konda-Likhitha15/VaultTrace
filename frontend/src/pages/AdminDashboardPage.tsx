import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAppContext } from '../context/AppContext';
import { apiErrorMessage, getAdminAnalytics } from '../services/api';
import type { AdminAnalytics, AdminAnalyticsBreakdown, AdminAnalyticsPoint, AnalyticsPeriod } from '../types';

const colors = ['#4f46e5', '#0f766e', '#d97706', '#be123c', '#7c3aed', '#0284c7', '#65a30d', '#c026d3'];

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(2)} GB`;
}

function ChartEmpty({ text = 'No records for this period.' }: { text?: string }) {
  return <div className="flex min-h-40 items-center justify-center rounded-lg bg-gray-50 p-5 text-center text-sm text-gray-500">{text}</div>;
}

function TrendLine({ points, bytes = false }: { points: AdminAnalyticsPoint[]; bytes?: boolean }) {
  if (!points.length) return <ChartEmpty />;
  const max = Math.max(1, ...points.map((point) => bytes ? point.bytes : point.count));
  const values = points.slice(-12);
  const coords = values.map((point, index) => `${30 + index * (330 / Math.max(values.length - 1, 1))},${112 - (bytes ? point.bytes : point.count) / max * 84}`).join(' ');
  return <svg aria-label={bytes ? 'Recorded uploaded bytes over time' : 'Records over time'} className="h-48 w-full" role="img" viewBox="0 0 380 150" preserveAspectRatio="none">
    <path d="M28 114H370M28 72H370M28 30H370" stroke="#e5e7eb" />
    <polyline fill="none" points={coords} stroke="#4f46e5" strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" />
    {values.map((point, index) => <g key={point.period}><circle cx={30 + index * (330 / Math.max(values.length - 1, 1))} cy={112 - (bytes ? point.bytes : point.count) / max * 84} r="4" fill="#4f46e5"><title>{point.period}: {bytes ? formatBytes(point.bytes) : point.count}</title></circle><text fill="#6b7280" fontSize="8" textAnchor="middle" x={30 + index * (330 / Math.max(values.length - 1, 1))} y="136">{point.period.slice(5)}</text></g>)}
  </svg>;
}

function Doughnut({ items, bytes = false, label }: { items: AdminAnalyticsBreakdown[]; bytes?: boolean; label: string }) {
  if (!items.length) return <ChartEmpty />;
  const total = items.reduce((sum, item) => sum + (bytes ? item.bytes : item.count), 0);
  if (!total) return <ChartEmpty />;
  let offset = 0;
  const slices = items.slice(0, 8).map((item, index) => {
    const count = bytes ? item.bytes : item.count;
    const dash = count / total * 100;
    const circle = <circle key={item.name} cx="58" cy="58" fill="none" r="40" stroke={colors[index % colors.length]} strokeDasharray={`${dash} ${100 - dash}`} strokeDashoffset={-offset} pathLength="100" strokeWidth="16"><title>{item.name}: {bytes ? formatBytes(count) : count}</title></circle>;
    offset += dash;
    return circle;
  });
  return <div className="flex flex-wrap items-center gap-4">
    <svg aria-label={label} className="h-32 w-32 shrink-0 -rotate-90" role="img" viewBox="0 0 116 116"><circle cx="58" cy="58" fill="none" r="40" stroke="#e5e7eb" strokeWidth="16" />{slices}</svg>
    <ul className="min-w-40 flex-1 space-y-2 text-xs">{items.slice(0, 8).map((item, index) => <li className="flex justify-between gap-3" key={item.name}><span className="flex min-w-0 items-center gap-2"><i aria-hidden="true" className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: colors[index % colors.length] }} /><span className="truncate">{item.name}</span></span><strong>{bytes ? formatBytes(item.bytes) : item.count}</strong></li>)}</ul>
  </div>;
}

function HorizontalBars({ items, bytes = true }: { items: AdminAnalyticsBreakdown[]; bytes?: boolean }) {
  if (!items.length) return <ChartEmpty />;
  const max = Math.max(1, ...items.map((item) => bytes ? item.bytes : item.count));
  return <ul className="space-y-3">{items.slice(0, 10).map((item, index) => {
    const amount = bytes ? item.bytes : item.count;
    return <li key={item.name} title={`${item.name}: ${bytes ? formatBytes(amount) : amount}`}><div className="mb-1 flex justify-between gap-3 text-xs"><span className="truncate">{item.name}</span><strong className="shrink-0">{bytes ? formatBytes(amount) : amount}</strong></div><div className="h-2.5 overflow-hidden rounded-full bg-gray-100"><div className="h-full rounded-full" style={{ width: `${amount / max * 100}%`, backgroundColor: colors[index % colors.length] }} /></div></li>;
  })}</ul>;
}

function PeriodBars({ points }: { points: AdminAnalyticsPoint[] }) {
  if (!points.length) return <ChartEmpty />;
  const values = points.slice(-12); const max = Math.max(1, ...values.map((point) => point.count));
  return <div className="flex h-44 items-end gap-2 overflow-x-auto border-b border-gray-200 px-1 pt-4">{values.map((point) => <div className="flex h-full min-w-7 flex-1 flex-col items-center justify-end gap-1" key={point.period} title={`${point.period}: ${point.count}`}><span className="text-[10px] text-gray-500">{point.count}</span><div className="w-full rounded-t bg-teal-700" style={{ height: `${Math.max(3, point.count / max * 78)}%` }} /><span className="pb-1 text-[9px] text-gray-500">{point.period.slice(5)}</span></div>)}</div>;
}

export function AdminDashboardPage() {
  const { token } = useAppContext();
  const [period, setPeriod] = useState<AnalyticsPeriod>('30d');
  const [analytics, setAnalytics] = useState<AdminAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!token) return;
    let active = true;
    setLoading(true); setError('');
    void getAdminAnalytics(token, period).then((data) => { if (active) setAnalytics(data); })
      .catch(async (reason: unknown) => { if (active) setError(await apiErrorMessage(reason, 'Administrator analytics could not be loaded.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, period, retry]);

  const cards = analytics ? [
    ['Registered users', analytics.total_registered_users], ['Active users', analytics.total_active_users],
    ['Inactive users', analytics.total_inactive_users], ['Pending applications', analytics.pending_applications],
    ['Documents', analytics.total_documents], ['Storage consumed', formatBytes(analytics.total_storage_bytes)],
    ['Shared documents', analytics.total_shared_documents], ['Storage remaining', analytics.storage_quota_bytes === null ? 'Not configured' : formatBytes(Math.max(0, analytics.storage_quota_bytes - analytics.total_storage_bytes))],
  ] : [];

  return <section className="space-y-7">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">Administration</p><h1 className="mt-1 text-3xl font-bold">Analytics overview</h1><p className="mt-2 text-gray-600">Live account, document, storage, and sharing measurements.</p></div><div className="flex flex-wrap gap-2"><label className="text-sm">Trend period<select aria-label="Analytics period" className="ml-2 rounded border bg-white px-3 py-2" onChange={(event) => setPeriod(event.target.value as AnalyticsPeriod)} value={period}><option value="7d">Last 7 days</option><option value="30d">Last 30 days</option><option value="90d">Last 90 days</option><option value="all">All time</option></select></label><Link className="rounded bg-indigo-700 px-3 py-2 text-sm font-semibold text-white" to="/admin/storage">Manage storage</Link></div></header>
    {loading && <p className="text-sm text-gray-600" role="status">Loading analytics…</p>}
    {error && <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-red-50 p-4 text-sm text-red-800" role="alert"><span>{error}</span><button className="rounded border px-3 py-1.5" disabled={loading} onClick={() => setRetry((value) => value + 1)} type="button">Retry</button></div>}
    {analytics && <>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{cards.map(([label, value]) => <article className="rounded-xl border bg-white p-4 shadow-sm" key={String(label)}><p className="text-sm text-gray-500">{label}</p><p className="mt-2 text-2xl font-bold">{value}</p></article>)}</div>
      <div className="grid gap-5 xl:grid-cols-2">
        <article className="rounded-xl border bg-white p-5"><h2 className="font-semibold">User registration trends</h2><p className="mt-1 text-xs text-gray-500">New user records by period.</p><TrendLine points={analytics.registration_trends} /></article>
        <article className="rounded-xl border bg-white p-5"><h2 className="font-semibold">Active versus inactive users</h2><p className="mt-1 text-xs text-gray-500">Active requires an active flag and ACTIVE account status.</p><Doughnut items={analytics.user_status} label="Active versus inactive user counts" /></article>
        <article className="rounded-xl border bg-white p-5"><h2 className="font-semibold">Document uploads over time</h2><p className="mt-1 text-xs text-gray-500">New document records by period.</p><TrendLine points={analytics.upload_trends} /></article>
        <article className="rounded-xl border bg-white p-5"><h2 className="font-semibold">Documents by file type</h2><p className="mt-1 text-xs text-gray-500">Current, non-deleted document records.</p><Doughnut items={analytics.file_types} label="Document counts by file type" /></article>
        <article className="rounded-xl border bg-white p-5"><h2 className="font-semibold">Recorded storage by organization</h2><p className="mt-1 text-xs text-gray-500">Includes retained previous versions and soft-deleted files.</p><HorizontalBars items={analytics.storage_by_organization} /></article>
        <article className="rounded-xl border bg-white p-5"><div className="flex items-center justify-between gap-3"><div><h2 className="font-semibold">Top users by recorded storage</h2><p className="mt-1 text-xs text-gray-500">Top 10 accounts; view all in storage management.</p></div><Link className="text-sm text-indigo-700 hover:underline" to="/admin/storage">View all</Link></div><HorizontalBars items={analytics.storage_by_user} /></article>
        <article className="rounded-xl border bg-white p-5"><h2 className="font-semibold">Document sharing activity</h2><p className="mt-1 text-xs text-gray-500">Share grants created in the selected period.</p><PeriodBars points={analytics.sharing_activity} /></article>
        <article className="rounded-xl border bg-white p-5"><h2 className="font-semibold">Monthly storage growth</h2><p className="mt-1 text-sm text-gray-700">Historical storage usage cannot be reconstructed from current records.</p><p className="mt-3 rounded-lg bg-amber-50 p-4 text-sm text-amber-900">{analytics.storage_growth_note}</p></article>
      </div>
      <nav aria-label="Administration shortcuts" className="flex flex-wrap gap-3"><Link className="rounded border bg-white px-4 py-3 text-sm font-medium" to="/admin/users">User management</Link><Link className="rounded border bg-white px-4 py-3 text-sm font-medium" to="/admin/applications">Review applications</Link><Link className="rounded border bg-white px-4 py-3 text-sm font-medium" to="/admin/audit-trail">Audit trail</Link></nav>
    </>}
  </section>;
}
