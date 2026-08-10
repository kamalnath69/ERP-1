import React, { createContext, useContext, useEffect, useCallback } from "react";
import { useDispatch, useSelector } from "react-redux";
import {
  fetchMe,
  loginThunk,
  registerOrgThunk,
  logoutThunk,
  selectAuth,
} from "@/store/slices/authSlice";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const dispatch = useDispatch();
  const { user, organization, permissions, roles, loading } = useSelector(selectAuth);

  const refreshMe = useCallback(async () => {
    await dispatch(fetchMe());
  }, [dispatch]);

  useEffect(() => {
    // The browser sends the HttpOnly access cookie automatically.
    dispatch(fetchMe());
  }, [dispatch]);

  const login = async (email, password, orgSlug, mfaCode) => {
    const result = await dispatch(loginThunk({ email, password, org_slug: orgSlug, mfa_code: mfaCode }));
    if (loginThunk.rejected.match(result)) {
      const err = new Error(result.payload?.detail || "Login failed");
      err.response = { data: result.payload, status: result.payload?.status };
      throw err;
    }
    return result.payload;
  };

  const registerOrg = async (payload) => {
    const result = await dispatch(registerOrgThunk(payload));
    if (registerOrgThunk.rejected.match(result)) {
      const err = new Error(result.payload?.detail || "Registration failed");
      err.response = { data: result.payload };
      throw err;
    }
    return result.payload;
  };

  const logout = async () => {
    await dispatch(logoutThunk());
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
