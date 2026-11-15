import { CAR_EMOJI, spriteOf } from "@/lib/villa";

// A loop on the town map (900×1200, in %): round the base and down to the beach road.
const ROUTE = "0%{left:31%;top:52%}22%{left:58%;top:52%}25%{left:60%;top:50%}47%{left:60%;top:35%}50%{left:57%;top:33%}72%{left:32%;top:33%}75%{left:30%;top:35%}97%{left:30%;top:50%}100%{left:31%;top:52%}";
const FLIP = "0%,24.9%{transform:translate(-50%,-50%) scaleX(-1)}25%,49.9%{transform:translate(-50%,-50%) scaleX(-1)}50%,74.9%{transform:translate(-50%,-50%)}75%,100%{transform:translate(-50%,-50%)}";

/** «Моя вилла»: the owner's chosen car driving its loop on the town map. */
export default function VillaCarDrive({ code }: { code: string }) {
  const sprite = spriteOf({ code, level: null });
  return (
    <span aria-hidden className="pointer-events-none absolute inset-0" data-testid="villa-car">
      <style>{`@keyframes villa-car-route{${ROUTE}}@keyframes villa-car-face{${FLIP}}`}</style>
      <span
        className="absolute"
        style={{ animation: "villa-car-route 28s linear infinite" }}
      >
        <span
          className="block text-2xl drop-shadow-[0_2px_2px_rgba(0,0,0,0.6)]"
          style={{ animation: "villa-car-face 28s steps(1) infinite" }}
        >
          {sprite ? <img src={sprite} alt="" className="h-9 w-auto" /> : CAR_EMOJI[code] ?? "🚗"}
        </span>
      </span>
    </span>
  );
}
