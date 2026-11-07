import { PasswordField } from './PasswordField';

type Props = { password: string; confirmPassword: string; onPassword: (value: string) => void; onConfirmPassword: (value: string) => void };

export function PasswordConfirmation({ password, confirmPassword, onPassword, onConfirmPassword }: Props) {
  return <>
    <PasswordField id="new-password" label="New password" autoComplete="new-password" minLength={12} value={password} onChange={onPassword} showStrength />
    <PasswordField id="confirm-new-password" label="Confirm new password" autoComplete="new-password" minLength={12} value={confirmPassword} onChange={onConfirmPassword} />
  </>;
}
