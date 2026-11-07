import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { loadCurrentUser, login as requestLogin, logout as requestLogout } from '../services/api';
import type { User } from '../types';

type AuthContextValue = {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<boolean>;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AppContextProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    function expireSession() {
      setToken(null);
      setUser(null);
    }
    window.addEventListener('vaulttrace:unauthorized', expireSession);
    return () => window.removeEventListener('vaulttrace:unauthorized', expireSession);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await requestLogin(email, password);
    setToken(result.access_token);
    setUser(result.user);
    return result.user;
  }, []);

  const logout = useCallback(async () => {
    const activeToken = token;
    setToken(null);
    setUser(null);
    if (!activeToken) return true;
    try {
      await requestLogout(activeToken);
      return true;
    } catch {
      // Local credentials are cleared regardless; callers can explain that
      // server-side revocation could not be confirmed.
      return false;
    }
  }, [token]);

  const refreshUser = useCallback(async () => {
    if (token) setUser(await loadCurrentUser(token));
  }, [token]);

  const value = useMemo(() => ({ user, token, login, logout, refreshUser }), [user, token, login, logout, refreshUser]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAppContext(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAppContext must be used inside AppContextProvider');
  return context;
}
