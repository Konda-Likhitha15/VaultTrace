import { expect, test, type Page } from '@playwright/test';

const dashboardCounts = {
  total_registered_users: 3,
  total_active_users: 2,
  total_pending_applications: 1,
  total_approved_users: 2,
  total_rejected_applications: 0,
  total_owners: 1,
  total_viewers: 1,
};

async function mockLogin(page: Page, role: 'Administrator' | 'Owner' | 'Viewer') {
  const user = {
    id: 10,
    email: `${role.toLowerCase()}@example.test`,
    full_name: 'Test User',
    username: `test-${role.toLowerCase()}`,
    role,
    account_status: 'ACTIVE',
  };
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/auth/login')) {
      await route.fulfill({ json: { access_token: 'mock-access-token', token_type: 'bearer', expires_at: '2099-01-01T00:00:00Z', user } });
    } else if (url.pathname.endsWith('/users/me')) {
      await route.fulfill({ json: user });
    } else if (url.pathname.endsWith('/admin/dashboard')) {
      await route.fulfill({ json: dashboardCounts });
    } else if (url.pathname.endsWith('/documents/')) {
      await route.fulfill({ json: [] });
    } else {
      await route.fulfill({ json: [] });
    }
  });
  await page.goto('/login');
  await page.getByLabel('Email').fill(user.email);
  await page.getByLabel('Password').fill('test-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
}

test('administrator sees administrator navigation', async ({ page }) => {
  await mockLogin(page, 'Administrator');
  const navigation = page.getByRole('navigation', { name: 'Admin navigation' });
  await expect(page).toHaveURL(/\/admin\/dashboard$/);
  await expect(navigation.getByRole('link', { name: 'All users' })).toBeVisible();
  await expect(navigation.getByRole('link', { name: 'Applications' })).toBeVisible();
  await expect(navigation.getByRole('link', { name: 'Documents & audit' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'User navigation' })).toHaveCount(0);
});

test('owner sees document controls and cannot open admin routes directly', async ({ page }) => {
  await mockLogin(page, 'Owner');
  const navigation = page.getByRole('navigation', { name: 'User navigation' });
  await expect(page).toHaveURL(/\/owner\/dashboard$/);
  await expect(navigation.getByRole('link', { name: 'My documents' })).toBeVisible();
  await expect(navigation.getByRole('link', { name: 'Upload documents' })).toBeVisible();
  await expect(navigation.getByRole('link', { name: 'Search documents' })).toBeVisible();
  await page.evaluate(() => {
    window.history.pushState({}, '', '/admin/accounts');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page).toHaveURL(/\/owner\/dashboard$/);
  await expect(page.getByRole('navigation', { name: 'Admin navigation' })).toHaveCount(0);
});

test('viewer sees authorized document navigation without upload controls', async ({ page }) => {
  await mockLogin(page, 'Viewer');
  const navigation = page.getByRole('navigation', { name: 'User navigation' });
  await expect(page).toHaveURL(/\/viewer\/dashboard$/);
  await expect(navigation.getByRole('link', { name: 'My documents' })).toBeVisible();
  await expect(navigation.getByRole('link', { name: 'Shared with me' })).toBeVisible();
  await expect(navigation.getByRole('link', { name: 'Upload documents' })).toHaveCount(0);
  await page.evaluate(() => {
    window.history.pushState({}, '', '/documents/upload');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page).toHaveURL(/\/documents$/);
});

test('owner upload, search and categories routes render distinct pages', async ({ page }) => {
  await mockLogin(page, 'Owner');
  const navigation = page.getByRole('navigation', { name: 'User navigation' });
  await navigation.getByRole('link', { name: 'Upload documents' }).click();
  await expect(page.getByRole('heading', { name: 'Upload documents' })).toBeVisible();
  await expect(page.getByText('Drag files here')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'My Documents' })).toHaveCount(0);

  await navigation.getByRole('link', { name: 'Search documents' }).click();
  await expect(page.getByRole('heading', { name: 'Search and Categories' })).toBeVisible();
  await expect(page.getByLabel('Document ID, name, or filename')).toBeVisible();

  await navigation.getByRole('link', { name: 'Categories' }).click();
  await expect(page.getByRole('heading', { name: 'Categories' })).toBeVisible();
});

test('shared documents page displays its explanatory empty state', async ({ page }) => {
  await mockLogin(page, 'Viewer');
  await page.getByRole('navigation', { name: 'User navigation' }).getByRole('link', { name: 'Shared with me' }).click();
  await expect(page.getByRole('heading', { name: 'Shared With Me' })).toBeVisible();
  await expect(page.getByText('No documents have been shared with you.')).toBeVisible();
});
