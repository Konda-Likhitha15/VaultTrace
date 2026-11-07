import { useState } from 'react';
import { passwordRequirements, passwordStrength } from '../utils/passwordPolicy';

type Props = {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: 'current-password' | 'new-password';
  required?: boolean;
  minLength?: number;
  maxLength?: number;
  showStrength?: boolean;
};

export function PasswordField({ id, label, value, onChange, autoComplete, required = true, minLength, maxLength = 128, showStrength = false }: Props) {
  const [visible, setVisible] = useState(false);
  const requirements = passwordRequirements(value);
  const strength = passwordStrength(value);
  const strengthText = strength <= 2 ? 'Weak' : strength <= 4 ? 'Getting stronger' : 'Strong';

  return <div>
    <label className="block text-sm font-medium" htmlFor={id}>{label}</label>
    <div className="relative mt-1">
      <input
        aria-describedby={showStrength ? `${id}-requirements` : undefined}
        autoComplete={autoComplete}
        className="w-full rounded border border-gray-300 px-3 py-2 pr-16"
        id={id}
        maxLength={maxLength}
        minLength={minLength}
        onChange={(event) => onChange(event.target.value)}
        required={required}
        type={visible ? 'text' : 'password'}
        value={value}
      />
      <button
        aria-label={`${visible ? 'Hide' : 'Show'} ${label.toLowerCase()}`}
        aria-pressed={visible}
        className="absolute inset-y-0 right-0 rounded-r border-l px-3 text-indigo-800 hover:bg-indigo-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-700"
        onClick={() => setVisible((current) => !current)}
        title={`${visible ? 'Hide' : 'Show'} ${label.toLowerCase()}`}
        type="button"
      >
        {visible ? <svg aria-hidden="true" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" d="M3 3l18 18M10.6 10.7a2 2 0 002.7 2.7M9.9 5.2A10.8 10.8 0 0112 5c5 0 8.5 4.5 9.5 7a11 11 0 01-3.1 4.2M6.2 6.3A11.8 11.8 0 002.5 12c1 2.5 4.5 7 9.5 7 1.1 0 2.1-.2 3-.6" /></svg> : <svg aria-hidden="true" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" d="M2.5 12s3.5-7 9.5-7 9.5 7 9.5 7-3.5 7-9.5 7-9.5-7-9.5-7z" /><circle cx="12" cy="12" r="3" strokeWidth="1.8" /></svg>}
      </button>
    </div>
    {showStrength && <div className="mt-2" id={`${id}-requirements`}>
      <div className="flex items-center gap-2" aria-live="polite">
        <div aria-label={`Password strength: ${strengthText}`} className="flex flex-1 gap-1" role="img">
          {requirements.map((item, index) => <span className={`h-1.5 flex-1 rounded ${index < strength ? (strength <= 2 ? 'bg-red-500' : strength <= 4 ? 'bg-amber-500' : 'bg-green-600') : 'bg-gray-200'}`} key={item.label} />)}
        </div>
        <span className="text-xs text-gray-600">{value ? strengthText : 'Not set'}</span>
      </div>
      <ul className="mt-2 grid gap-x-3 gap-y-1 text-xs text-gray-600 sm:grid-cols-2">
        {requirements.map((item) => <li className={item.met ? 'text-green-800' : ''} key={item.label}>{item.met ? '✓' : '•'} {item.label}</li>)}
      </ul>
    </div>}
  </div>;
}
