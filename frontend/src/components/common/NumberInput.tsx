import { useEffect, useRef, useState } from "react";

interface NumberInputProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  className?: string;
  placeholder?: string;
}

const DEFAULT_CLASS = "rounded-lg bg-bg-surface px-3 py-2 outline-none";

function formatValue(value: number): string {
  return Number.isFinite(value) ? String(value) : "";
}

// Keeps its own text while focused so clearing/typing decimals doesn't snap back to "0"; syncs to `value` on blur.
export default function NumberInput({ value, onChange, min, max, step, className, placeholder }: NumberInputProps) {
  const [text, setText] = useState(() => formatValue(value));
  const focused = useRef(false);

  useEffect(() => {
    if (!focused.current) setText(formatValue(value));
  }, [value]);

  const clamp = (n: number) => {
    let next = n;
    if (min !== undefined) next = Math.max(min, next);
    if (max !== undefined) next = Math.min(max, next);
    return next;
  };

  return (
    <input
      type="text"
      inputMode={step !== undefined && step < 1 ? "decimal" : "numeric"}
      placeholder={placeholder}
      value={text}
      onFocus={() => { focused.current = true; }}
      onChange={(e) => {
        const raw = e.target.value;
        if (raw !== "" && !/^-?\d*\.?\d*$/.test(raw)) return;
        setText(raw);
        if (raw !== "" && raw !== "-" && !raw.endsWith(".")) {
          const n = Number(raw);
          if (Number.isFinite(n)) onChange(clamp(n));
        }
      }}
      onBlur={() => {
        focused.current = false;
        const n = Number(text);
        const next = text === "" || !Number.isFinite(n) ? clamp(min ?? 0) : clamp(n);
        onChange(next);
        setText(formatValue(next));
      }}
      className={className ?? DEFAULT_CLASS}
    />
  );
}
