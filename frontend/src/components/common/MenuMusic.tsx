import { useEffect } from "react";
import { useLocation } from "react-router-dom";

import { installMusic, isMusicRoute, setMusicRoute } from "@/lib/music";

/** Keeps the menu music in step with the screen (see `lib/music.ts`). */
export default function MenuMusic() {
  const { pathname } = useLocation();
  useEffect(() => installMusic(), []);
  useEffect(() => setMusicRoute(isMusicRoute(pathname)), [pathname]);
  return null;
}
