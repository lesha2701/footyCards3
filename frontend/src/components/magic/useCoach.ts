import { useState } from "react";

const read = (key: string) => {
  try {
    return window.localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
};

const write = (key: string) => {
  try {
    window.localStorage.setItem(key, "1");
  } catch {
    /* private mode: the hints just show again next time */
  }
};

/** Step-by-step hints shown once (remembered per device), reopened with «?». */
export function useCoach(key: string) {
  const [open, setOpen] = useState(() => !read(key));
  return {
    open,
    show: () => setOpen(true),
    close: () => {
      write(key);
      setOpen(false);
    },
  };
}
