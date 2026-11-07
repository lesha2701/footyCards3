import type { ReactNode } from "react";

import warBackground from "@/assets/clubs/war-bg.webp";

/** The «Клубная война» stadium behind the score. The art is night-dark in
 * both themes, so whatever sits on it uses white text, not the theme's ink. */
export function ClubWarArt({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`relative isolate overflow-hidden rounded-3xl bg-[#07090c] ${className}`}>
      <img src={warBackground} alt="" aria-hidden className="absolute inset-0 -z-10 h-full w-full object-cover object-[center_62%]" />
      <div className="absolute inset-0 -z-10 bg-gradient-to-b from-black/30 via-black/15 to-black/55" />
      {children}
    </div>
  );
}
