import { createClient, type SupabaseClient } from "@supabase/supabase-js";

export interface PublicSupabaseConfig {
  url: string;
  publishableKey: string;
}

export function readPublicSupabaseConfig(): PublicSupabaseConfig | null {
  const url = import.meta.env.VITE_SUPABASE_URL?.trim();
  const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!url || !publishableKey) {
    return null;
  }
  return { url, publishableKey };
}

export function createPublicSupabaseClient(
  config: PublicSupabaseConfig,
): SupabaseClient {
  return createClient(config.url, config.publishableKey, {
    auth: {
      autoRefreshToken: true,
      detectSessionInUrl: true,
      persistSession: true,
    },
  });
}

const config = readPublicSupabaseConfig();
export const supabase = config ? createPublicSupabaseClient(config) : null;
