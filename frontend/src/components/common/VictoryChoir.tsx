import { useEffect } from "react";

import { playChoir } from "@/lib/music";

/** Rendered with a win or a legendary card: the «Campeones» choir sings once. */
export default function VictoryChoir() {
  useEffect(() => playChoir(), []);
  return null;
}
