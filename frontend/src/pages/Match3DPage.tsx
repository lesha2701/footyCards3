import { useNavigate } from "react-router-dom";

import Match3DGame from "@/components/match3d/Match3DGame";

/** «Матч 3D»: a short 11-a-side match in landscape. No rewards yet. */
export default function Match3DPage() {
  const navigate = useNavigate();
  return <Match3DGame onExit={() => navigate("/play")} />;
}
