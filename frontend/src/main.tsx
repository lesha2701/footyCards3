import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "framer-motion";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { useAdminToastStore } from "@/admin/adminToastStore";
import App from "@/App";
import ErrorBoundary from "@/components/common/ErrorBoundary";
import { ApiRequestError } from "@/lib/api";
import "@/index.css";

// Every mutation in the admin panel (save/update/delete/etc.) gets a generic
// success/error toast automatically, so an admin never has to guess whether
// a click registered — the alternative was pages wiring this individually
// per mutation, which is how the balance-adjustment page ended up with none
// and got triple-clicked. Gated to /admin so the regular Mini App (which
// already has its own per-action feedback/animations) is unaffected.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 15_000,
      refetchOnWindowFocus: false,
    },
  },
  mutationCache: new MutationCache({
    onSuccess: () => {
      if (window.location.pathname.startsWith("/admin")) {
        useAdminToastStore.getState().push("Изменения сохранены", "success");
      }
    },
    onError: (error) => {
      if (window.location.pathname.startsWith("/admin")) {
        const message = error instanceof ApiRequestError ? error.message : "Не удалось сохранить изменения";
        useAdminToastStore.getState().push(message, "error");
      }
    },
  }),
});

// index.html's start-up guard: from here on, failures are the app's own to show.
(window as Window & { __appStarted?: boolean }).__appStarted = true;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        {/* Honour the OS "reduce motion" setting for every framer-motion
            animation in one place: transforms/layout animations are
            skipped, opacity fades still run. */}
        <MotionConfig reducedMotion="user">
          <ErrorBoundary>
            <App />
          </ErrorBoundary>
        </MotionConfig>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
