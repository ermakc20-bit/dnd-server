import { useEffect, useState } from "react";
export function useDevice() {
  const [width, setWidth] = useState(window.innerWidth);
  useEffect(() => {
    const resize = () => setWidth(window.innerWidth);
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);
  return width < 768 ? "phone" : width < 1280 ? "tablet" : "desktop";
}
