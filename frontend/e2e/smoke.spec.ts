import { expect, test } from '@playwright/test';

test('shows the common sign-in page by default', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
});

test('signup requires email verification before submission', async ({ page }) => {
  await page.goto('/signup');
  await expect(page.getByRole('heading', { name: 'Apply for an account' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Send OTP' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Submit signup application' })).toBeDisabled();
});

test('login password starts hidden and can be revealed accessibly', async ({ page }) => {
  await page.goto('/login');
  const password = page.getByLabel('Password');
  await expect(password).toHaveAttribute('type', 'password');
  await page.getByRole('button', { name: 'Show password' }).click();
  await expect(password).toHaveAttribute('type', 'text');
  await expect(page.getByRole('button', { name: 'Hide password' })).toHaveAttribute('aria-pressed', 'true');
});

test('signup shows password requirements and strength as the user types', async ({ page }) => {
  await page.goto('/signup');
  const password = page.getByLabel('Password', { exact: true });
  await expect(password).toHaveAttribute('type', 'password');
  await expect(page.getByText('At least 12 characters')).toBeVisible();
  await password.fill('short');
  await expect(page.getByRole('img', { name: 'Password strength: Weak' })).toBeVisible();
  await password.fill('SecurePassphrase12!');
  await expect(page.getByRole('img', { name: 'Password strength: Strong' })).toBeVisible();
});
