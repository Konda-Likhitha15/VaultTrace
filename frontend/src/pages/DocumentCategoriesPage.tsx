import { useEffect, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { useAppContext } from '../context/AppContext';
import { getDocumentCategories, searchDocuments } from '../services/api';
import type { DocumentSearchResult } from '../types';

export function DocumentCategoriesPage() {
  const { token } = useAppContext();
  const [categories, setCategories] = useState<string[]>([]);
  const [selected, setSelected] = useState('');
  const [documents, setDocuments] = useState<DocumentSearchResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token) return;
    let active = true;
    setLoading(true);
    void getDocumentCategories(token).then((items) => {
      if (!active) return;
      setCategories(items);
      setSelected(items[0] ?? '');
    }).catch((reason: unknown) => {
      if (active) setError(axios.isAxiosError(reason) && typeof reason.response?.data?.detail === 'string' ? reason.response.data.detail : 'Categories could not be loaded.');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token]);

  useEffect(() => {
    if (!token || !selected) { setDocuments([]); return; }
    let active = true;
    setLoading(true); setError('');
    void searchDocuments(token, { category: selected, limit: 100, sort_by: 'document_name', sort_order: 'asc' })
      .then((items) => { if (active) setDocuments(items); })
      .catch((reason: unknown) => { if (active) setError(axios.isAxiosError(reason) && typeof reason.response?.data?.detail === 'string' ? reason.response.data.detail : 'Category documents could not be loaded.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, selected]);

  return <main className="mx-auto max-w-5xl">
    <header><p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">Documents</p><h1 className="mt-1 text-3xl font-bold">Categories</h1><p className="mt-2 text-gray-600">Categories are derived only from documents you are authorized to discover.</p></header>
    {error && <p className="mt-5 rounded bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}
    {loading && !categories.length ? <p className="mt-6" role="status">Loading categories…</p> : categories.length === 0 ? <div className="mt-6 rounded-xl border border-dashed p-8 text-center"><p className="font-medium">No document categories yet.</p><Link className="mt-3 inline-block text-indigo-700 underline" to="/documents/upload">Upload Document</Link></div> : <>
      <nav aria-label="Document categories" className="mt-6 flex flex-wrap gap-2">{categories.map((category) => <button className={`rounded-full border px-4 py-2 text-sm ${selected === category ? 'border-indigo-700 bg-indigo-50 font-semibold text-indigo-800' : ''}`} key={category} onClick={() => setSelected(category)} type="button">{category}</button>)}</nav>
      <h2 className="mt-7 text-xl font-semibold">{selected}</h2>
      {loading ? <p className="mt-4" role="status">Loading category documents…</p> : documents.length === 0 ? <div className="mt-4 rounded-xl border border-dashed p-7 text-gray-600">No documents in this category.</div> : <ul className="mt-4 divide-y rounded-xl border bg-white">{documents.map((item) => <li className="flex flex-wrap items-center justify-between gap-3 p-4" key={item.id}><div><p className="font-medium">{item.document_name}</p><p className="mt-1 break-all text-xs text-gray-500">{item.id} · {item.original_filename} · {item.access_level}</p></div><Link className="rounded border px-3 py-2 text-sm" to="/documents/search">Search documents</Link></li>)}</ul>}
    </>}
  </main>;
}
