import { useEffect, useState } from "react";

export type ProductRoute = { kind: "home" } | { kind: "room"; id: string } | { kind: "join"; token: string } | { kind: "missing" };
export function productRoute(path: string): ProductRoute {
  if (path === "/") return { kind: "home" };
  const match = path.match(/^\/(rooms|join)\/([^/]+)\/?$/);
  if (!match) return { kind: "missing" };
  try {
    const value = decodeURIComponent(match[2]);
    if (!/^[A-Za-z0-9_-]{1,512}$/.test(value)) return { kind: "missing" };
    return match[1] === "rooms" ? { kind: "room", id: value } : { kind: "join", token: value };
  } catch { return { kind: "missing" }; }
}
export function safeReturnPath(path: string): string {
  return productRoute(path).kind === "missing" ? "/" : path;
}
export function useProductRoute() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const read = () => setPath(window.location.pathname);
    window.addEventListener("popstate", read);
    return () => window.removeEventListener("popstate", read);
  }, []);
  function navigate(next: string) {
    const safe = safeReturnPath(next);
    window.history.pushState(null, "", safe);
    setPath(safe);
  }
  return { route: productRoute(path), path, navigate };
}
