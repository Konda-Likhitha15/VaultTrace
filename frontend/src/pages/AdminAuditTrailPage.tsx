import { useEffect, useState } from 'react';
import { useAppContext } from '../context/AppContext';
import { apiErrorMessage, exportAuditLogs, getAuditLogs, getAuditSummary } from '../services/api';
import type { AuditEvent, AuditFilters, AuditLogPage, AuditSummary } from '../types';

const PAGE_SIZE = 25;

function reportDate(value: FormDataEntryValue | null, end = false): string | undefined {
  const date = String(value ?? '').trim();
  return date ? `${date}T${end ? '23:59:59' : '00:00:00'}Z` : undefined;
}

function safeJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

export function AdminAuditTrailPage() {
  const { token } = useAppContext();
  const [filters, setFilters] = useState<AuditFilters>({});
  const [page, setPage] = useState<AuditLogPage | null>(null);
  const [summary, setSummary] = useState<AuditSummary | null>(null);
  const [selected, setSelected] = useState<AuditEvent | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [offset, setOffset] = useState(0);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!token) return;
    let active = true;
    setLoading(true);
    setError('');
    void Promise.all([getAuditLogs(token, filters, offset, PAGE_SIZE), getAuditSummary(token, filters)])
      .then(([nextPage, nextSummary]) => {
        if (active) { setPage(nextPage); setSummary(nextSummary); }
      })
      .catch(async (reason: unknown) => { if (active) setError(await apiErrorMessage(reason, 'Audit records could not be loaded.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, filters, offset, reload]);

  function applyFilters(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const userId = String(values.get('user_id') ?? '').trim();
    const organizationId = String(values.get('organization_id') ?? '').trim();
    const action = String(values.get('action') ?? '').trim();
    const search = String(values.get('search') ?? '').trim();
    const resourceId = String(values.get('resource_id') ?? '').trim();
    const outcome = String(values.get('outcome') ?? '').trim();
    setFilters({
      user_id: userId ? Number(userId) : undefined,
      organization_id: organizationId ? Number(organizationId) : undefined,
      action: action || undefined,
      search: search || undefined,
      resource_id: resourceId || undefined,
      outcome: outcome ? outcome as AuditFilters['outcome'] : undefined,
      date_from: reportDate(values.get('date_from')),
      date_to: reportDate(values.get('date_to'), true),
    });
    setOffset(0);
  }

  async function downloadCsv() {
    if (!token) return;
    setExporting(true); setError(''); setNotice('');
    try {
      const blob = await exportAuditLogs(token, filters);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url; anchor.download = 'vaulttrace-audit-logs.csv'; anchor.click();
      URL.revokeObjectURL(url);
      setNotice('Audit CSV export downloaded.');
    } catch (reason) { setError(await apiErrorMessage(reason, 'Audit CSV export failed.')); }
    finally { setExporting(false); }
  }

  const cards: Array<[string, number | undefined]> = [
    ['Total audit events', summary?.total_events],
    ['Successful operations', summary?.successful_operations],
    ['Failed operations', summary?.failed_operations],
    ['Unique active users', summary?.active_users],
  ];

  return <main className="mx-auto max-w-7xl">
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div><p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">Administration</p><h1 className="mt-1 text-3xl font-bold">Audit Trail</h1><p className="mt-2 text-gray-600">Review recorded authentication, document, permission, and administration events.</p></div>
      <div className="flex gap-2"><button className="rounded border px-3 py-2 text-sm" disabled={loading || exporting} onClick={() => setReload((current) => current + 1)} type="button">Refresh</button><button className="rounded bg-indigo-700 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={loading || exporting} onClick={() => void downloadCsv()} type="button">{exporting ? 'Preparing CSV…' : 'Export CSV'}</button></div>
    </header>

    {error && <p className="mt-5 rounded bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}
    {notice && <p className="mt-5 rounded bg-green-50 p-3 text-sm text-green-800" role="status">{notice}</p>}

    <section aria-label="Audit summary" className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map(([label, value]) => <article className="rounded-xl border bg-white p-4 shadow-sm" key={label}><p className="text-sm text-gray-600">{label}</p><p className="mt-2 text-2xl font-semibold">{loading && value === undefined ? '…' : value ?? 0}</p></article>)}
    </section>

    <form className="mt-6 grid gap-3 rounded-xl border bg-white p-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6" onSubmit={applyFilters}>
      <label className="text-sm font-medium">Actor user ID<input className="mt-1 w-full rounded border px-3 py-2" min="1" name="user_id" type="number" /></label>
      <label className="text-sm font-medium">Organization ID<input className="mt-1 w-full rounded border px-3 py-2" min="1" name="organization_id" type="number" /></label>
      <label className="text-sm font-medium">Action<input className="mt-1 w-full rounded border px-3 py-2" maxLength={64} name="action" placeholder="e.g. DOCUMENT_UPLOADED" /></label>
      <label className="text-sm font-medium">Search<input className="mt-1 w-full rounded border px-3 py-2" maxLength={100} name="search" placeholder="Actor, action, resource…" /></label>
      <label className="text-sm font-medium">Outcome<select className="mt-1 w-full rounded border px-3 py-2" defaultValue="" name="outcome"><option value="">All outcomes</option><option value="SUCCESS">Success</option><option value="FAILURE">Failure</option></select></label>
      <label className="text-sm font-medium">Document / resource ID<input className="mt-1 w-full rounded border px-3 py-2" maxLength={64} name="resource_id" /></label>
      <label className="text-sm font-medium">From date<input className="mt-1 w-full rounded border px-3 py-2" name="date_from" type="date" /></label>
      <label className="text-sm font-medium">To date<input className="mt-1 w-full rounded border px-3 py-2" name="date_to" type="date" /></label>
      <div className="flex gap-2 xl:col-span-6"><button className="rounded bg-indigo-700 px-4 py-2 text-sm font-semibold text-white" type="submit">Apply filters</button><button className="rounded border px-4 py-2 text-sm" type="reset" onClick={() => { setFilters({}); setOffset(0); }}>Clear filters</button></div>
    </form>

    <section className="mt-6 rounded-xl border bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-xl font-semibold">Audit activity</h2><p className="text-sm text-gray-600">{page?.total ?? 0} matching events</p></div>
      {loading ? <p className="mt-5 text-gray-600" role="status">Loading audit events…</p> : !page?.items.length ? <p className="mt-5 rounded border border-dashed p-8 text-center text-gray-600">No audit events match these filters.</p> : <div className="mt-4 overflow-x-auto"><table className="min-w-[850px] w-full text-left text-sm"><thead className="bg-gray-50 text-xs uppercase text-gray-600"><tr><th className="p-3">Date and time</th><th className="p-3">User</th><th className="p-3">Action</th><th className="p-3">Resource</th><th className="p-3">Outcome</th><th className="p-3">Organization</th><th className="p-3">Details</th></tr></thead><tbody className="divide-y">{page.items.map((event) => <tr key={event.id}><td className="whitespace-nowrap p-3">{new Date(event.occurred_at).toLocaleString()}</td><td className="p-3">{event.actor_email ?? event.actor_username ?? (event.actor_id ? `User #${event.actor_id}` : 'Unknown account')}</td><td className="p-3">{event.action}</td><td className="p-3"><span>{event.resource_type ?? '—'}</span>{event.resource_id && <span className="ml-1 break-all text-xs text-gray-500">{event.resource_id}</span>}</td><td className="p-3"><span className={`rounded-full px-2 py-1 text-xs ${event.outcome === 'SUCCESS' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>{event.outcome}</span></td><td className="p-3">{event.organization_name ?? (event.organization_id ? `#${event.organization_id}` : '—')}</td><td className="p-3"><button className="rounded border px-2 py-1" onClick={() => setSelected(event)} type="button">View</button></td></tr>)}</tbody></table></div>}
      <div className="mt-4 flex justify-between"><button className="rounded border px-3 py-2 text-sm disabled:opacity-50" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} type="button">Previous</button><span className="self-center text-sm text-gray-600">Page {Math.floor(offset / PAGE_SIZE) + 1}</span><button className="rounded border px-3 py-2 text-sm disabled:opacity-50" disabled={loading || !page || offset + PAGE_SIZE >= page.total} onClick={() => setOffset(offset + PAGE_SIZE)} type="button">Next</button></div>
    </section>

    {selected && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"><section aria-labelledby="audit-event-title" aria-modal="true" className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white p-5" role="dialog"><header className="flex justify-between gap-4"><div><p className="text-xs uppercase tracking-wide text-gray-500">Audit event #{selected.id}</p><h2 className="mt-1 text-xl font-semibold" id="audit-event-title">{selected.action}</h2></div><button aria-label="Close event details" className="rounded border px-3 py-1" onClick={() => setSelected(null)} type="button">Close</button></header><dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2"><div><dt className="text-gray-500">Actor</dt><dd>{selected.actor_email ?? selected.actor_username ?? selected.actor_id ?? 'Unknown account'}</dd></div><div><dt className="text-gray-500">Outcome</dt><dd>{selected.outcome}</dd></div><div><dt className="text-gray-500">Resource</dt><dd>{selected.resource_type ?? '—'} {selected.resource_id ?? ''}</dd></div><div><dt className="text-gray-500">Organization</dt><dd>{selected.organization_name ?? selected.organization_id ?? '—'}</dd></div><div><dt className="text-gray-500">Timestamp (UTC)</dt><dd>{new Date(selected.occurred_at).toLocaleString()}</dd></div><div><dt className="text-gray-500">Request source</dt><dd>{selected.request_ip ?? '—'}</dd></div><div className="sm:col-span-2"><dt className="text-gray-500">User agent</dt><dd className="break-all">{selected.user_agent ?? '—'}</dd></div></dl><h3 className="mt-5 font-semibold">Safe metadata</h3><pre className="mt-2 overflow-x-auto rounded bg-gray-50 p-3 text-xs">{safeJson(selected.details)}</pre>{(selected.previous_state || selected.new_state) && <div className="mt-4 grid gap-4 sm:grid-cols-2"><div><h3 className="font-semibold">Previous state summary</h3><pre className="mt-2 overflow-x-auto rounded bg-gray-50 p-3 text-xs">{safeJson(selected.previous_state)}</pre></div><div><h3 className="font-semibold">New state summary</h3><pre className="mt-2 overflow-x-auto rounded bg-gray-50 p-3 text-xs">{safeJson(selected.new_state)}</pre></div></div>}</section></div>}
  </main>;
}
