import { useMemo, useState } from "react";

export function useSort<T>(rows: T[], initial: keyof T & string, dir: "asc" | "desc" = "desc") {
  const [key, setKey] = useState<string>(initial);
  const [d, setD] = useState<"asc" | "desc">(dir);
  const sorted = useMemo(() => {
    const m = d === "asc" ? 1 : -1;
    return [...rows].sort((a: any, b: any) => {
      const x = a[key], y = b[key];
      return (typeof x === "string" ? x.localeCompare(y) : x - y) * m;
    });
  }, [rows, key, d]);
  const toggle = (k: string) => {
    if (k === key) setD(d === "asc" ? "desc" : "asc");
    else { setKey(k); setD("desc"); }
  };
  const arrow = (k: string) => (k === key ? (d === "asc" ? " ▲" : " ▼") : "");
  return { sorted, toggle, arrow };
}
