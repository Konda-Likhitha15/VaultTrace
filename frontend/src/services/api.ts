import axios from 'axios';
import type { AdminActionResponse, AdminApplication, AdminOverview, AdminUser, TokenResponse, User } from '../types';

export const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1' });

export async function login(email: string, password: string): Promise<TokenResponse> {
  const response = await api.post('/auth/login', { email, password });
  return response.data as TokenResponse;
}

export async function logout(token: string): Promise<void> {
  await api.post('/auth/logout', undefined, { headers: { Authorization: `Bearer ${token}` } });
}

export async function loadCurrentUser(token: string) {
  const response = await api.get('/users/me', { headers: { Authorization: `Bearer ${token}` } });
  return response.data as User;
}

export async function requestEmailOtp(email: string, resend = false): Promise<void> {
  void resend;
  await api.post('/auth/signup/send-otp', { email });
}

export async function verifyEmailOtp(email: string, otp: string): Promise<void> {
  await api.post('/auth/signup/verify-otp', { email, otp });
}

export async function requestPasswordReset(email: string): Promise<void> {
  await api.post('/auth/forgot-password', { email });
}

export async function verifyPasswordResetOtp(email: string, otp: string): Promise<{ authorization_token: string; expires_in_seconds: number }> {
  return (await api.post('/auth/verify-reset-otp', { email, otp })).data;
}

export async function submitPasswordReset(authorization_token: string, password: string, confirm_password: string): Promise<void> {
  await api.post('/auth/reset-password', { authorization_token, password, confirm_password });
}

export async function submitRegistration(payload: {
  full_name: string;
  username: string;
  email: string;
  phone_number?: string;
  password: string;
  confirm_password: string;
}): Promise<{ message: string; application_id: number; approval_status: string }> {
  const response = await api.post('/auth/register', payload);
  return response.data;
}

function authHeaders(token: string) {
  return { headers: { Authorization: `Bearer ${token}` } };
}

export async function getAdminOverview(token: string): Promise<AdminOverview> {
  return (await api.get('/admin/dashboard', authHeaders(token))).data as AdminOverview;
}

export async function getAdminUsers(token: string): Promise<AdminUser[]> {
  return (await api.get('/admin/users', authHeaders(token))).data as AdminUser[];
}

export async function getAdminApplications(token: string): Promise<AdminApplication[]> {
  return (await api.get('/admin/applications', authHeaders(token))).data as AdminApplication[];
}

export async function approveAdminApplication(token: string, id: number, role: 'Owner' | 'Viewer'): Promise<AdminActionResponse> {
  return (await api.post(`/admin/applications/${id}/approve`, { role }, authHeaders(token))).data as AdminActionResponse;
}

export async function rejectAdminApplication(token: string, id: number, reason: string): Promise<AdminActionResponse> {
  return (await api.post(`/admin/applications/${id}/reject`, { reason }, authHeaders(token))).data as AdminActionResponse;
}

export async function updateAdminUserRole(token: string, id: number, role: 'Owner' | 'Viewer'): Promise<AdminUser> {
  return (await api.patch(`/admin/users/${id}/role`, { role }, authHeaders(token))).data as AdminUser;
}

export async function updateAdminUserStatus(token: string, id: number, status: 'ACTIVE' | 'INACTIVE' | 'SUSPENDED'): Promise<AdminUser> {
  return (await api.patch(`/admin/users/${id}/status`, { status }, authHeaders(token))).data as AdminUser;
}
