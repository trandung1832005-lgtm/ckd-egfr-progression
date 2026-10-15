"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, ApiError } from "./api";
import type { Me, Role } from "./types";

interface AuthState {
  user: Me | null;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
  setUser: (u: Me | null) => void;
}

const Ctx = createContext<AuthState | null>(null);

export const homeFor = (role: Role) => (role === "patient" ? "/patient" : role === "doctor" ? "/doctor" : "/admin");

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setUser(await api<Me>("/api/auth/me"));
    } catch (e) {
      if (!(e instanceof ApiError) || e.status === 401 || e.status === 0) setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch {
      /* dù lỗi mạng vẫn xóa trạng thái cục bộ */
    }
    setUser(null);
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- nạp phiên đăng nhập hiện có khi mở trang
    void refresh();
  }, [refresh]);

  return <Ctx.Provider value={{ user, loading, refresh, logout, setUser }}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth phải nằm trong AuthProvider");
  return v;
}
