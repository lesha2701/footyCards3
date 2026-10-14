import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

import { DIE_PIPS } from "./magnateMeta";

function Die({ value, rolling }: { value: number; rolling: boolean }) {
  const pips = DIE_PIPS[value] ?? [];
  return (
    <motion.span
      animate={rolling ? { rotate: [0, -25, 20, -10, 0], y: [0, -10, 0, -4, 0] } : { rotate: 0, y: 0 }}
      transition={{ duration: 0.6 }}
      className="grid h-10 w-10 grid-cols-3 grid-rows-3 gap-[2px] rounded-lg bg-white p-[5px] shadow-md"
    >
      {Array.from({ length: 9 }, (_, i) => (
        <span key={i} className={`rounded-full ${pips.includes(i) ? "bg-slate-900" : ""}`} />
      ))}
    </motion.span>
  );
}

/** Two dice; when `rollN` changes they tumble through random faces for a
 *  moment and land on the server's result (the result itself is never
 *  decided here). */
export default function MagnateDice({ dice, rollN }: { dice: number[] | null; rollN: number | null }) {
  const [faces, setFaces] = useState<number[]>(dice ?? [1, 1]);
  const [rolling, setRolling] = useState(false);
  const seenN = useRef<number | null>(rollN);

  useEffect(() => {
    if (!dice) return;
    if (rollN === seenN.current) {
      setFaces(dice);
      return;
    }
    seenN.current = rollN;
    setRolling(true);
    const spin = setInterval(() => setFaces([1 + Math.floor(Math.random() * 6), 1 + Math.floor(Math.random() * 6)]), 90);
    const stop = setTimeout(() => {
      clearInterval(spin);
      setFaces(dice);
      setRolling(false);
    }, 600);
    return () => {
      clearInterval(spin);
      clearTimeout(stop);
      setRolling(false);
    };
  }, [dice, rollN]);

  return (
    <div className="flex gap-2">
      <Die value={faces[0]} rolling={rolling} />
      <Die value={faces[1]} rolling={rolling} />
    </div>
  );
}
