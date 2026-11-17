import { motion } from "framer-motion";
import { useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

/**
 * A full-screen layer for the magic sheets and popups.
 * - Rendered into <body>: a transformed ancestor would otherwise trap `position: fixed`.
 * - Ignores clicks in its first 400 ms: on Android the tap that opened it lands on it again
 *   and would close it at once.
 */
export function Backdrop({ onClick, className, children }: { onClick: () => void; className: string; children: ReactNode }) {
  const opened = useRef(Date.now());
  return createPortal(
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      onClick={() => { if (Date.now() - opened.current > 400) onClick(); }} className={className}>
      {children}
    </motion.div>,
    document.body,
  );
}
