import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useAuthStore } from "@/store/authStore";

export default function AdminGuard({ children }: { children: ReactNode }) {
  const user = useAuthStore((s) => s.user);
  const adminToken = useAuthStore((s) => s.adminToken);

  if (!user?.is_admin || !adminToken) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
