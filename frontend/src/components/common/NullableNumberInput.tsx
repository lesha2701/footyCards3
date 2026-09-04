import { useEffect, useRef, useState } from "react";

interface NullableNumberInputProps {
  value: number | null;
  onChange: (value: number | null) => void;
  min?: number;
  max?: number;
  className?: string;
  placeholder?: string;
}

const DEFAULT_CLASS = "rounded-lg bg-bg-surface px-3 py-2 outline-none";

function formatValue(value: number | null): string {
  return value === null || !Number.isFinite(value) ? "" : String(value);
}

// Like NumberInput, but an empty field means "unset" (null) instead of
// snapping to `min` — used where a blank/dash value has real meaning (e.g.
// "this rarity can't be used here") rather than just being invalid input.
export default function NullableNumberInput({ value, onChange, min, max, className, placeholder }: NullableNumberInputProps) {
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
      inputMode="numeric"
      placeholder={placeholder ?? "—"}
      value={text}
      onFocus={() => { focused.current = true; }}
      onChange={(e) => {
        const raw = e.target.value;
        if (raw !== "" && !/^\d*$/.test(raw)) return;
        setText(raw);
        if (raw !== "") {
          const n = Number(raw);
          if (Number.isFinite(n)) onChange(clamp(n));
        }
      }}
      onBlur={() => {
        focused.current = false;
        if (text === "") {
          onChange(null);
          return;
        }
        const n = Number(text);
        const next = Number.isFinite(n) ? clamp(n) : null;
        onChange(next);
        setText(formatValue(next));
      }}
      className={className ?? DEFAULT_CLASS}
    />
  );
}
