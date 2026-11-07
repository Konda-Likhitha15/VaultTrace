import { useEffect, useState, type FormEvent } from 'react';
import { DocumentPreviewDialog } from '../components/DocumentPreviewDialog';
import { useAppContext } from '../context/AppContext';
import { apiErrorMessage, downloadDocument, searchDocuments } from '../services/api';
import type { DocumentFilters, DocumentMetadata, DocumentSearchResult } from '../types';

export function DocumentSearchPage() {
  const { token } = useAppContext();
  const [filters, setFilters] = useState<DocumentFilters>({ sort_by: 'created_at', sort_order: 'desc', limit: 25, offset: 0 });
  const [results, setResults] = useState<DocumentSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [hasSearched, setHasSearched] = useState(false);
  const [preview, setPreview] = useState<DocumentMetadata | null>(null);

  async function runSearch(next: DocumentFilters) {
    if (!token) return;
    setLoading(true); setError(''); setHasSearched(true);
    try { setResults(await searchDocuments(token, next)); }
    catch (reason) { setError(await apiErrorMessage(reason, 'Search failed.')); setResults([]); }
    finally { setLoading(false); }
  }

  useEffect(() => { void runSearch(filters); }, [token, filters.offset]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const next: DocumentFilters = {
      search: String(values.get('search') ?? '').trim() || undefined,
      category: String(values.get('category') ?? '').trim() || undefined,
      file_type: String(values.get('file_type') ?? '').trim() || undefined,
      owner_id: Number(values.get('owner_id')) || undefined,
      visibility: String(values.get('visibility') ?? '') as DocumentFilters['visibility'] || undefined,
      access_status: String(values.get('access_status') ?? '') as DocumentFilters['access_status'] || undefined,
      date_from: String(values.get('date_from') ?? '') || undefined,
      date_to: String(values.get('date_to') ?? '') || undefined,
      sort_by: String(values.get('sort_by') ?? 'created_at') as DocumentFilters['sort_by'],
      sort_order: String(values.get('sort_order') ?? 'desc') as DocumentFilters['sort_order'],
      limit: 25,
      offset: 0,
    };
    setFilters(next);
    void runSearch(next);
  }

  async function download(item: DocumentSearchResult) {
    if (!token) return;
    try {
      const blob = await downloadDocument(token, item.id);
      const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = item.original_filename; anchor.click(); URL.revokeObjectURL(url);
    } catch (reason) { setError(await apiErrorMessage(reason, 'Download failed.')); }
  }

  function clear() {
    const form = document.querySelector<HTMLFormElement>('#document-search-form'); form?.reset();
    const next = { sort_by: 'created_at' as const, sort_order: 'desc' as const, limit: 25, offset: 0 };
    setFilters(next); void runSearch(next);
  }

  function changePage(delta: number) {
    setFilters((current) => ({ ...current, offset: Math.max(0, (current.offset ?? 0) + delta) }));
  }

  return <main className="mx-auto max-w-6xl">
    <header><p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">Documents</p><h1 className="mt-1 text-3xl font-bold">Search and Categories</h1><p className="mt-2 text-gray-600">Search by document ID, document name, or original filename. Results include only documents you can access.</p></header>
    <form id="document-search-form" className="mt-6 grid gap-3 rounded-xl border bg-white p-4 sm:grid-cols-2 lg:grid-cols-4" onSubmit={submit}>
      <label className="text-sm font-medium sm:col-span-2">Document ID, name, or filename<input className="mt-1 w-full rounded border px-3 py-2" name="search" type="search" placeholder="Paste UUID or search names" /></label>
      <label className="text-sm font-medium">Category<input className="mt-1 w-full rounded border px-3 py-2" name="category" placeholder="Any category" /></label>
      <label className="text-sm font-medium">File type<input className="mt-1 w-full rounded border px-3 py-2" name="file_type" placeholder="pdf, docx…" /></label>
      <label className="text-sm font-medium">Owner ID<input className="mt-1 w-full rounded border px-3 py-2" name="owner_id" min="1" type="number" /></label>
      <label className="text-sm font-medium">Visibility<select className="mt-1 w-full rounded border px-3 py-2" name="visibility"><option value="">Any</option><option>PRIVATE</option><option>SHARED</option><option>RESTRICTED</option></select></label>
      <label className="text-sm font-medium">Access status<select className="mt-1 w-full rounded border px-3 py-2" name="access_status"><option value="">Any</option><option value="OWNED">Owned</option><option value="SHARED">Shared with me</option></select></label>
      <label className="text-sm font-medium">Uploaded from<input className="mt-1 w-full rounded border px-3 py-2" name="date_from" type="date" /></label>
      <label className="text-sm font-medium">Uploaded to<input className="mt-1 w-full rounded border px-3 py-2" name="date_to" type="date" /></label>
      <label className="text-sm font-medium">Sort by<select className="mt-1 w-full rounded border px-3 py-2" name="sort_by"><option value="created_at">Upload date</option><option value="document_name">Document name</option><option value="file_size">File size</option></select></label>
      <label className="text-sm font-medium">Order<select className="mt-1 w-full rounded border px-3 py-2" name="sort_order"><option value="desc">Descending</option><option value="asc">Ascending</option></select></label>
      <div className="flex items-end gap-2 lg:col-span-4"><button className="rounded bg-indigo-700 px-4 py-2 font-semibold text-white disabled:opacity-50" disabled={loading} type="submit">{loading ? 'Searching…' : 'Search'}</button><button className="rounded border px-4 py-2 disabled:opacity-50" disabled={loading} onClick={clear} type="button">Clear filters</button></div>
    </form>
    {error && <p className="mt-4 rounded bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}
    {loading && <p className="mt-5 text-gray-600" role="status">Searching authorized documents…</p>}
    {!loading && hasSearched && !results.length && <div className="mt-6 rounded-xl border border-dashed p-8 text-center"><p className="font-medium">No matching documents found.</p><p className="mt-1 text-sm text-gray-600">Try another name, ID, or filter. Unauthorized documents are never included.</p></div>}
    {!loading && results.length > 0 && <><div className="mt-6 grid gap-4 md:grid-cols-2">{results.map((item) => <article className="rounded-xl border bg-white p-5" key={item.id}>
      <div className="flex items-start justify-between gap-3"><div><h2 className="font-semibold">{item.document_name}</h2><p className="mt-1 break-all text-xs text-gray-500">ID {item.id}</p></div><span className="rounded bg-indigo-50 px-2 py-1 text-xs text-indigo-800">{item.access_level}</span></div>
      <dl className="mt-4 grid grid-cols-2 gap-2 text-sm"><div><dt className="text-xs text-gray-500">Owner</dt><dd>{item.owner_name} (@{item.owner_username})</dd></div><div><dt className="text-xs text-gray-500">Category / type</dt><dd>{item.category} · {item.file_extension.toUpperCase()}</dd></div><div><dt className="text-xs text-gray-500">Visibility</dt><dd>{item.visibility}</dd></div><div><dt className="text-xs text-gray-500">Uploaded</dt><dd>{new Date(item.created_at).toLocaleDateString()}</dd></div></dl>
      <div className="mt-4 flex gap-2"><button className="rounded bg-indigo-700 px-3 py-2 text-sm text-white" onClick={() => setPreview(item)} type="button">Preview</button><button className="rounded border px-3 py-2 text-sm" onClick={() => void download(item)} type="button">Download</button></div>
    </article>)}</div><div className="mt-5 flex justify-between"><button className="rounded border px-3 py-2 text-sm disabled:opacity-50" disabled={!filters.offset || loading} onClick={() => changePage(-25)} type="button">Previous</button><button className="rounded border px-3 py-2 text-sm disabled:opacity-50" disabled={results.length < 25 || loading} onClick={() => changePage(25)} type="button">Next</button></div></>}
    {preview && token && <DocumentPreviewDialog token={token} document={preview} onClose={() => setPreview(null)} />}
  </main>;
}
