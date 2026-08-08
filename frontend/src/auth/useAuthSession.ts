import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";

import { supabase } from "../lib/supabase";

export type AuthState =
  | { status: "misconfigured"; session: null }
  | { status: "loading"; session: null }
  | { status: "anonymous"; session: null }
  | { status: "authenticated"; session: Session };

export function useAuthSession(): AuthState {
  const [state, setState] = useState<AuthState>(() =>
    supabase
      ? { status: "loading", session: null }
      : { status: "misconfigured", session: null },
  );

  useEffect(() => {
    if (!supabase) {
      return undefined;
    }

    void supabase.auth.getSession().then(({ data }) => {
      setState(
        data.session
          ? { status: "authenticated", session: data.session }
          : { status: "anonymous", session: null },
      );
    });

    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      setState(
        session
          ? { status: "authenticated", session }
          : { status: "anonymous", session: null },
      );
    });

    return () => data.subscription.unsubscribe();
  }, []);

  return state;
}
