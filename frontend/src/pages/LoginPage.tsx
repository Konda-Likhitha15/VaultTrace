import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { useAppContext } from '../context/AppContext';

export function LoginPage() {
  const { user, login } = useAppContext();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to={user.role === 'Administrator' ? '/admin/dashboard' : user.role === 'Owner' ? '/owner/dashboard' : '/viewer/dashboard'} replace />;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const signedInUser = await login(email, password);
      navigate(signedInUser.role === 'Administrator' ? '/admin/dashboard' : signedInUser.role === 'Owner' ? '/owner/dashboard' : '/viewer/dashboard', { replace: true });
    } catch {
      setError('Unable to sign in. Check your email and password, then try again.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <section className="w-full max-w-md rounded-xl bg-white p-8 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">VaultTrace</p>
        <h1 className="mt-2 text-3xl font-bold">Sign in</h1>
        <p className="mt-2 text-gray-600">Access your secure document workspace.</p>
        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="email">Email</label>
            <input className="w-full rounded border border-gray-300 px-3 py-2" id="email" type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="password">Password</label>
            <input className="w-full rounded border border-gray-300 px-3 py-2" id="password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
          </div>
          {error && <p className="text-sm text-red-700" role="alert">{error}</p>}
          <button className="w-full rounded bg-indigo-700 px-4 py-2 font-semibold text-white disabled:opacity-60" type="submit" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <p className="mt-5 text-center text-sm text-gray-600">Need an account? <Link className="font-medium text-indigo-700 hover:underline" to="/signup">Apply for access</Link></p>
        <p className="mt-2 text-center text-sm"><Link className="font-medium text-indigo-700 hover:underline" to="/forgot-password">Forgot password?</Link></p>
      </section>
    </main>
  );
}
