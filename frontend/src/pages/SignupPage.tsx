import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { requestEmailOtp, submitRegistration, verifyEmailOtp } from '../services/api';
import { OtpVerification } from '../components/OtpVerification';

function errorText(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      const messages = detail.flatMap((issue: unknown) => {
        if (typeof issue !== 'object' || issue === null) return [];
        const item = issue as { loc?: unknown; msg?: unknown };
        if (typeof item.msg !== 'string') return [];
        const location = Array.isArray(item.loc)
          ? item.loc.filter((part): part is string | number => typeof part === 'string' || typeof part === 'number').filter((part) => part !== 'body').join('.')
          : 'form';
        return [`${location || 'form'}: ${item.msg}`];
      });
      if (messages.length > 0) return messages.join(' ');
    }
    if (!error.response) return 'Cannot reach the VaultTrace API. Check that the backend is running at http://localhost:8000 and that this page is opened from http://localhost:5173.';
    if (error.response.status >= 500) return 'The backend could not process this request. Check that PostgreSQL is running and the latest Alembic migrations are applied.';
    return `The request failed (HTTP ${error.response.status}). Check the entered email and try again.`;
  }
  return 'Something went wrong. Please try again.';
}

export function SignupPage() {
  const [fullName, setFullName] = useState('');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [otpSent, setOtpSent] = useState(false);
  const [otpSentAt, setOtpSentAt] = useState(0);
  const [emailVerified, setEmailVerified] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState<'send' | 'verify' | 'signup' | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function sendCode(resend: boolean) {
    setError('');
    setNotice('');
    if (!email) {
      setError('Enter your email address first.');
      return;
    }
    setBusy('send');
    try {
      await requestEmailOtp(email, resend);
      setOtpSent(true);
      setOtpSentAt(Date.now());
      setEmailVerified(false);
      setNotice('If this address can be registered, a verification code has been sent.');
    } catch (requestError) {
      setError(errorText(requestError));
    } finally {
      setBusy(null);
    }
  }

  async function verifyCode() {
    setError('');
    setNotice('');
    setBusy('verify');
    try {
      await verifyEmailOtp(email, otp);
      setEmailVerified(true);
      setNotice('Email verified. Complete the form and submit your application.');
    } catch (requestError) {
      setError(errorText(requestError));
    } finally {
      setBusy(null);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setNotice('');
    if (!emailVerified) {
      setError('Verify your email before submitting.');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    setBusy('signup');
    try {
      const result = await submitRegistration({
        full_name: fullName,
        username,
        email,
        phone_number: phoneNumber || undefined,
        password,
        confirm_password: confirmPassword,
      });
      setSubmitted(true);
      setNotice(result.message);
    } catch (requestError) {
      setError(errorText(requestError));
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="min-h-screen px-4 py-10">
      <section className="mx-auto max-w-2xl rounded-xl bg-white p-6 shadow-sm sm:p-8">
        <p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">VaultTrace</p>
        <h1 className="mt-2 text-3xl font-bold">Apply for an account</h1>
        <p className="mt-2 text-gray-600">Verify your email before your application is sent for administrator review.</p>
        {submitted ? (
          <div className="mt-6 rounded-lg border border-green-200 bg-green-50 p-4" role="status">
            <h2 className="font-semibold text-green-900">Registration submitted</h2>
            <p className="mt-1 text-green-800">Your account remains inactive until an administrator reviews your application.</p>
            <Link className="mt-3 inline-block font-medium text-indigo-700 hover:underline" to="/login">Return to sign in</Link>
          </div>
        ) : (
          <form className="mt-6 grid gap-4 sm:grid-cols-2" onSubmit={submit}>
            <label className="text-sm font-medium sm:col-span-2">Full name
              <input className="mt-1 w-full rounded border border-gray-300 px-3 py-2" autoComplete="name" maxLength={160} required value={fullName} onChange={(event) => setFullName(event.target.value)} />
            </label>
            <label className="text-sm font-medium">Username
              <input className="mt-1 w-full rounded border border-gray-300 px-3 py-2" autoComplete="username" minLength={3} maxLength={32} pattern="[A-Za-z0-9_.-]+" required value={username} onChange={(event) => setUsername(event.target.value)} />
            </label>
            <label className="text-sm font-medium">Phone number <span className="font-normal text-gray-500">(optional)</span>
              <input className="mt-1 w-full rounded border border-gray-300 px-3 py-2" autoComplete="tel" maxLength={32} type="tel" value={phoneNumber} onChange={(event) => setPhoneNumber(event.target.value)} />
            </label>
            <label className="text-sm font-medium sm:col-span-2">Email
              <div className="mt-1 flex flex-col gap-2 sm:flex-row">
                <input className="min-w-0 flex-1 rounded border border-gray-300 px-3 py-2" autoComplete="email" required type="email" value={email} onChange={(event) => { setEmail(event.target.value); setEmailVerified(false); setOtpSent(false); }} />
                <button className="rounded border border-indigo-700 px-3 py-2 font-medium text-indigo-700 disabled:opacity-60" type="button" disabled={busy !== null || emailVerified} onClick={() => void sendCode(false)}>
                  {emailVerified ? 'Email verified' : busy === 'send' ? 'Sending…' : 'Send OTP'}
                </button>
              </div>
            </label>
            {otpSent && <OtpVerification key={otpSentAt} value={otp} onChange={setOtp} onVerify={() => void verifyCode()} onResend={() => void sendCode(true)} busy={busy !== null} verified={emailVerified} sentAt={otpSentAt} />}
            <label className="text-sm font-medium">Password
              <input className="mt-1 w-full rounded border border-gray-300 px-3 py-2" autoComplete="new-password" minLength={12} maxLength={128} required type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
              <span className="mt-1 block text-xs font-normal text-gray-500">Use at least 12 characters.</span>
            </label>
            <label className="text-sm font-medium">Confirm password
              <input className="mt-1 w-full rounded border border-gray-300 px-3 py-2" autoComplete="new-password" minLength={12} maxLength={128} required type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} />
            </label>
            {error && <p className="rounded bg-red-50 p-3 text-sm text-red-800 sm:col-span-2" role="alert">{error}</p>}
            {notice && <p className="rounded bg-blue-50 p-3 text-sm text-blue-800 sm:col-span-2" role="status">{notice}</p>}
            <button className="rounded bg-indigo-700 px-4 py-3 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60 sm:col-span-2" type="submit" disabled={busy !== null || !emailVerified}>
              {busy === 'signup' ? 'Submitting…' : 'Submit signup application'}
            </button>
          </form>
        )}
        {!submitted && <p className="mt-5 text-center text-sm text-gray-600">Already have an account? <Link className="font-medium text-indigo-700 hover:underline" to="/login">Sign in</Link></p>}
      </section>
    </main>
  );
}
