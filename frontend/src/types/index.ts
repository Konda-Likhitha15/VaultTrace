export type HealthStatus = { status: string };

export type RoleName = 'Administrator' | 'Owner' | 'Viewer';
export type User = {
  id: number;
  email: string;
  full_name: string;
  username: string;
  role: RoleName;
  account_status: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: 'bearer';
  expires_at: string;
  user: User;
};

export type AdminOverview = {
  total_registered_users: number;
  total_active_users: number;
  total_pending_applications: number;
  total_approved_users: number;
  total_rejected_applications: number;
  total_owners: number;
  total_viewers: number;
};

export type AdminUser = {
  id: number;
  full_name: string;
  username: string;
  email: string;
  phone_number: string | null;
  role: RoleName;
  email_verified: boolean;
  account_status: string;
  registration_date: string;
};

export type AdminApplication = {
  id: number;
  user_id: number;
  full_name: string;
  username: string;
  email: string;
  phone_number: string | null;
  email_verified: boolean;
  approval_status: 'PENDING' | 'APPROVED' | 'REJECTED';
  submitted_at: string;
  reviewed_by_id: number | null;
  reviewed_at: string | null;
  assigned_role: RoleName | null;
  rejection_reason: string | null;
};

export type AdminActionResponse = { message: string; notification_sent: boolean | null };
