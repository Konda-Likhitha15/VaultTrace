type Props = { password: string; confirmPassword: string; onPassword: (value: string) => void; onConfirmPassword: (value: string) => void };

export function PasswordConfirmation({ password, confirmPassword, onPassword, onConfirmPassword }: Props) {
  return <>
    <label className="text-sm font-medium">New password
      <input className="mt-1 w-full rounded border border-gray-300 px-3 py-2" autoComplete="new-password" minLength={12} maxLength={128} required type="password" value={password} onChange={(event) => onPassword(event.target.value)} />
    </label>
    <label className="text-sm font-medium">Confirm new password
      <input className="mt-1 w-full rounded border border-gray-300 px-3 py-2" autoComplete="new-password" minLength={12} maxLength={128} required type="password" value={confirmPassword} onChange={(event) => onConfirmPassword(event.target.value)} />
    </label>
  </>;
}
