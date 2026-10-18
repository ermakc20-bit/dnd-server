// Explicit local acceptance entry; production main.tsx never imports this fixture.
import { createRoot } from "react-dom/client";
import type { Session } from "@supabase/supabase-js";
import { AppView } from "../src/App";
import "../src/styles.css";
const guest = window.location.pathname.startsWith("/join/");
const session = { access_token: "local-t09-gm" } as Session;
createRoot(document.getElementById("root")!).render(<AppView auth={guest
  ? { status: "anonymous", session: null } : { status: "authenticated", session }} />);
