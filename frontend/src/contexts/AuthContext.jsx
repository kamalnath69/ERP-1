import React, { createContext, useContext, useEffect, useCallback } from "react";
import { useDispatch, useSelector } from "react-redux";
import { tokenStore } from "@/lib/api";
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
    // Bootstrap: always try fetchMe once; it will resolve loading=false either way.
    if (tokenStore.get()) {
      dispatch(fetchMe());
    } else {
      dispatch(fetchMe()); // will 401 -> reducer clears loading
    }
  }, [dispatch]);

  const login = async (email, password) => {
    const result = await dispatch(loginThunk({ email, password }));
    if (loginThunk.rejected.match(result)) {
      const err = new Error(result.payload?.detail || "Login failed");
      err.response = { data: result.payload };
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
