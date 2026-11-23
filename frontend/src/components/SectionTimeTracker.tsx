import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

import { apiUrl, buildAuthHeaders } from "@/lib/api";
import { FLUSH_MS, SectionClock, TICK_MS, sectionOf } from "@/lib/sectionTime";

const visible = () => document.visibilityState === "visible";

/** Sends the active time per section (lib/sectionTime.ts). Renders nothing. */
export default function SectionTimeTracker() {
  const { pathname } = useLocation();
  const clock = useRef<SectionClock | null>(null);
  if (clock.current === null) clock.current = new SectionClock(sectionOf(pathname), Date.now());

  useEffect(() => {
    clock.current?.setSection(sectionOf(pathname), Date.now(), visible());
  }, [pathname]);

  useEffect(() => {
    const c = clock.current!;
    const flush = () => {
      const sections = c.take();
      if (Object.keys(sections).length === 0) return;
      // keepalive: the batch sent from pagehide / a hidden page still arrives.
      fetch(apiUrl("/activity/time"), {
        method: "POST",
        headers: { ...buildAuthHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ sections }),
        keepalive: true,
      }).catch(() => {});
    };
    const onInput = () => c.input(Date.now(), visible());
    const onVisibility = () => {
      // The interval up to now was spent on the side we are leaving.
      const nowVisible = visible();
      c.tick(Date.now(), !nowVisible);
      if (!nowVisible) flush();
    };
    const onPageHide = () => {
      c.tick(Date.now(), true);
      flush();
    };
    const tick = window.setInterval(() => c.tick(Date.now(), visible()), TICK_MS);
    const send = window.setInterval(flush, FLUSH_MS);
    const events = ["pointerdown", "keydown", "wheel", "touchmove"] as const;
    events.forEach((e) => window.addEventListener(e, onInput, { passive: true }));
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", onPageHide);
    return () => {
      window.clearInterval(tick);
      window.clearInterval(send);
      events.forEach((e) => window.removeEventListener(e, onInput));
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", onPageHide);
    };
  }, []);

  return null;
}
