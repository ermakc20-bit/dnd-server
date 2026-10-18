// Explicit local fixture: production main.tsx never imports this module.
import { createRoot } from "react-dom/client";
import type { Session } from "../../frontend/node_modules/@supabase/supabase-js";
import { AppView } from "../../frontend/src/App";
import "../../frontend/src/styles.css";
const guest = location.pathname.startsWith("/join/");
const bootstrap = guest ? null : await (await fetch("/__e2e/bootstrap")).json();
createRoot(document.getElementById("root")!).render(<AppView auth={guest
  ? { status: "anonymous", session: null }
  : { status: "authenticated", session: { access_token: bootstrap.token } as Session }} />);
