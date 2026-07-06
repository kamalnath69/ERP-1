import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import api, { tokenStore } from "@/lib/api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [organization, setOrganization] = useState(null);
  const [permissions, setPermissions] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);

  const refreshMe = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data.user);
      setOrganization(data.organization);
      setPermissions(data.permissions || []);
      setRoles(data.roles || []);
    } catch {
      setUser(null);
      setOrganization(null);
      setPermissions([]);
      setRoles([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tokenStore.get()) refreshMe();
    else setLoading(false);
  }, [refreshMe]);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    tokenStore.set(data.access_token);
    tokenStore.setRefresh(data.refresh_token);
    await refreshMe();
    return data.user;
  };

  const registerOrg = async (payload) => {
    const { data } = await api.post("/auth/register", payload);
    tokenStore.set(data.access_token);
    tokenStore.setRefresh(data.refresh_token);
    await refreshMe();
    return data.user;
  };

  const logout = async () => {
    try {
      await api.post("/auth/logout", { refresh_token: tokenStore.getRefresh() });
    } catch {}
    tokenStore.clear();
    setUser(null);
    setOrganization(null);
    setPermissions([]);
    setRoles([]);
  };

  const can = (code) => user?.is_super_admin || permissions.includes(code);
  const hasAny = (...codes) => user?.is_super_admin || codes.some((c) => permissions.includes(c));

  return (
    <AuthCtx.Provider
      value={{ user, organization, permissions, roles, loading, login, registerOrg, logout, refreshMe, can, hasAny }}
    >
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() {
  return useContext(AuthCtx);
}
