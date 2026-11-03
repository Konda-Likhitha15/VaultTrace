import { useEffect, useState } from 'react';
import axios from 'axios';
import { searchDocumentPreview } from '../services/api';
import type { DocumentMetadata } from '../types';

export function DocumentPreviewDialog({ token, document, onClose }: { token: string; document: DocumentMetadata; onClose: () => void }) {
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    let objectUrl = '';
    void searchDocumentPreview(token, document.id).then((blob) => {
      objectUrl = URL.createObjectURL(blob);
      if (active) setUrl(objectUrl);
      else URL.revokeObjectURL(objectUrl);
    }).catch((reason: unknown) => {
      if (active) setError(axios.isAxiosError(reason) && typeof reason.response?.data?.detail === 'string' ? reason.response.data.detail : 'Preview could not be loaded.');
    });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [token, document.id]);

  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section aria-modal="true" aria-labelledby="document-preview-title" className="flex max-h-[90vh] w-full max-w-5xl flex-col rounded-xl bg-white p-4 shadow-xl" role="dialog">
      <header className="flex items-center justify-between gap-4"><h2 className="font-semibold" id="document-preview-title">Preview: {document.document_name}</h2><button className="rounded border px-3 py-1" onClick={onClose} type="button">Close</button></header>
      {error ? <p className="mt-4 rounded bg-red-50 p-3 text-red-800" role="alert">{error}</p> : url ? <iframe className="mt-4 min-h-[65vh] w-full rounded border" title={`Preview of ${document.document_name}`} src={url} /> : <p className="mt-6" role="status">Loading authorized preview…</p>}
    </section>
  </div>;
}
