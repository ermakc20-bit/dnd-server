import type { CSSProperties } from "react";

const paths = {
  check: "m5 12 4 4L19 6",
  line: "m5 19 14-14",
  direction: "M5 19 19 5M9 5h10v10",
  label: "M4 5h16M12 5v15m-4 0h8",
  fog: "M4 8V4h4m8 0h4v4m0 8v4h-4M8 20H4v-4M4 12h.01M12 4h.01M20 12h.01M12 20h.01",
  polygon: "m4 7 10-3 7 10-10 7-7-14Zm10-3v.01M4 7v.01m17 7v.01m-10 7v.01",
  close: "m6 6 12 12M6 18 18 6",
  search: "m21 21-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z",
  pointer: "m5 3 14 9-7 1-3 7-4-17Z",
  ruler: "m3 16 13-13 5 5L8 21l-5-5Zm5-5 3 3m1-7 3 3",
  arrow: "M19 12H5m6-6-6 6 6 6",
  chevron: "m9 5 7 7-7 7",
  plus: "M12 5v14M5 12h14",
  map: "m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6Zm6-3v15m6-12v15",
  cards: "M7 3h12a2 2 0 0 1 2 2v12M5 7h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2Z",
  tools: "m4 20 7-7m-4-7 3-3 11 11-3 3L7 6Zm7 1 3-3m1 7 3-3M3 3l18 18",
  upload: "M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5",
  people: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  settings: "M4 7h16M4 17h16M8 4v6m8 4v6",
  refresh: "M20 7v5h-5M4 17v-5h5m-4.7-4a8 8 0 0 1 13.2-3L20 8M4 16l2.5 3A8 8 0 0 0 19.7 16",
  dice: "m12 2 9 5v10l-9 5-9-5V7l9-5Zm0 0L7 16h10L12 2ZM3 7l4 9-4 1m18-10-4 9 4 1M7 16l5 6 5-6M3 7l9 3 9-3",
} as const;

export type IconName = keyof typeof paths;

export function Icon({ name, size = 20, style }: { name: keyof typeof paths; size?: number; style?: CSSProperties }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" style={style}>
    <path d={paths[name]} />
  </svg>;
}
