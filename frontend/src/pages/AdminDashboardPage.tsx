import { useEffect, useState } from 'react';
import axios from 'axios';
import { getAdminOverview } from '../services/api';
import { useAppContext } from '../context/AppContext';
import type { AdminOverview } from '../types';

const metrics: Array<[keyof AdminOverview, string]> = [
  ['total_registered_users', 'Registered users'],
  ['total_active_users', 'Active users'],
  ['total_pending_applications', 'Pending applications'],
  ['total_approved_users', 'Approved users'],
  ['total_rejected_applications', 'Rejected applications'],
  ['total_owners', 'Owners'],
  ['total_viewers', 'Viewers'],
];

export function AdminDashboardPage() {
  const { token } = useAppContext();
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token) return;
    void getAdminOverview(token).then(setOverview).catch((reason: unknown) => {
      setError(axios.isAxiosError(reason) && reason.response?.status === 403 ? 'Administrator access is required.' : 'Could not load dashboard data.');
    });
  }, [token]);

  return <section>
    <h1 className="text-2xl font-bold sm:text-3xl">Overview</h1>
    <p className="mt-2 text-gray-600">Live account and application totals.</p>
    {error && <p className="mt-5 rounded bg-red-50 p-3 text-red-800" role="alert">{error}</p>}
    {!overview && !error && <p className="mt-6 text-gray-600" role="status">Loading dashboard…</p>}
    {overview && <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {metrics.map(([key, label]) => <article className="rounded-xl border border-gray-200 bg-white p-5" key={key}>
        <p className="text-sm text-gray-600">{label}</p><p className="mt-2 text-3xl font-bold">{overview[key]}</p>
      </article>)}
    </div>}
  </section>;
}
