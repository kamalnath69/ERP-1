import React, { createContext, useContext, useEffect, useCallback } from "react";
import { useDispatch, useSelector } from "react-redux";
import {
  fetchMe,
  loginThunk,
  registerOrgThunk,
  logoutThunk,
  selectAuth,
} from "@/store/slices/authSlice";
import { baseApi } from "@/store/api/baseApi";

const AuthCtx = createContext(null);

function rejectedActionError(result, fallback) {
  const payload = result.payload || {};
  const error = new Error(payload.detail || fallback);
  error.code = payload.code || null;
  error.response = { data: payload, status: payload.status ?? null };
  return error;
}

export function AuthProvider({ children }) {
  const dispatch = useDispatch();
  const { user, organization, permissions, roles, accessContext, loading } = useSelector(selectAuth);

  const refreshMe = useCallback(async () => {
    await dispatch(fetchMe());
  }, [dispatch]);

  useEffect(() => {
    // The browser sends the HttpOnly access cookie automatically.
    dispatch(fetchMe());
  }, [dispatch]);

  useEffect(() => {
    const refreshAccess = () => {
      dispatch(baseApi.util.resetApiState());
      dispatch(fetchMe());
    };
    window.addEventListener("edvatiq:access-changed", refreshAccess);
    return () => window.removeEventListener("edvatiq:access-changed", refreshAccess);
  }, [dispatch]);

  const login = async (email, password, orgSlug, mfaCode) => {
    const result = await dispatch(loginThunk({ email, password, org_slug: orgSlug, mfa_code: mfaCode }));
    if (loginThunk.rejected.match(result)) {
      throw rejectedActionError(result, "Login failed");
    }
    return result.payload;
  };

  const registerOrg = async (payload) => {
    const result = await dispatch(registerOrgThunk(payload));
    if (registerOrgThunk.rejected.match(result)) {
      throw rejectedActionError(result, "Registration failed");
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
      value={{ user, organization, permissions, roles, accessContext, loading, login, registerOrg, logout, refreshMe, can, hasAny }}
    >
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() {
  return useContext(AuthCtx);
}
