import { getSupabaseBrowserClient } from "@/lib/supabase";

export type AppUser = {
  id: string;
  email: string;
  createdAt: string;
};

export type FavoritePlayer = {
  id: number;
  name: string;
  team: string;
  position: string;
  headshotUrl: string;
  number?: string | null;
  bats?: string | null;
  throws?: string | null;
  hitting?: Record<string, string | number> | null;
  pitching?: Record<string, string | number> | null;
};

export type FavoritesState = {
  teamIds: string[];
  players: FavoritePlayer[];
};

type AuthResult = { ok: true; message?: string } | { ok: false; error: string };

type FavoriteRow = {
  team_ids: string[] | null;
  players: FavoritePlayer[] | null;
};

function missingSupabaseError() {
  return "Supabase is not configured yet. Add NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in Vercel (then redeploy).";
}

function friendlyAuthError(error: { message?: string } | null | undefined): string {
  const message = (error?.message || "").trim() || "Login failed.";
  // Browser TypeError when DNS/network can't reach the Supabase project URL.
  if (/failed to fetch|networkerror|load failed|fetch failed/i.test(message)) {
    return (
      "Can't reach Supabase (Failed to fetch). Your project URL is missing, paused, or deleted. " +
      "In Supabase → Project Settings → API, copy Project URL + anon public key into Vercel env vars, then redeploy."
    );
  }
  if (/invalid api key|jwt/i.test(message)) {
    return "Supabase rejected the API key. Re-copy the anon public key into NEXT_PUBLIC_SUPABASE_ANON_KEY in Vercel and redeploy.";
  }
  return message;
}

function toAppUser(user: { id: string; email?: string; created_at?: string } | null): AppUser | null {
  if (!user?.email) {
    return null;
  }

  return {
    id: user.id,
    email: user.email,
    createdAt: user.created_at ?? new Date().toISOString()
  };
}

export async function getSession(): Promise<AppUser | null> {
  const supabase = getSupabaseBrowserClient();

  if (!supabase) {
    return null;
  }

  const { data } = await supabase.auth.getUser();
  return toAppUser(data.user);
}

export async function signUp(email: string, password: string): Promise<AuthResult> {
  const normalizedEmail = email.trim().toLowerCase();

  if (!normalizedEmail || !password) {
    return { ok: false, error: "Email and password are required." };
  }

  if (password.length < 6) {
    return { ok: false, error: "Password must be at least 6 characters." };
  }

  const supabase = getSupabaseBrowserClient();

  if (!supabase) {
    return { ok: false, error: missingSupabaseError() };
  }

  try {
    const { data, error } = await supabase.auth.signUp({
      email: normalizedEmail,
      password
    });

    if (error) {
      return { ok: false, error: friendlyAuthError(error) };
    }

    return {
      ok: true,
      message: data.session ? "Account created." : "Account created. Check your email to confirm your signup."
    };
  } catch (err) {
    return {
      ok: false,
      error: friendlyAuthError({
        message: err instanceof Error ? err.message : "Failed to fetch"
      })
    };
  }
}

export async function signIn(email: string, password: string): Promise<AuthResult> {
  const normalizedEmail = email.trim().toLowerCase();

  const supabase = getSupabaseBrowserClient();

  if (!supabase) {
    return { ok: false, error: missingSupabaseError() };
  }

  try {
    const { error } = await supabase.auth.signInWithPassword({
      email: normalizedEmail,
      password
    });

    if (error) {
      return { ok: false, error: friendlyAuthError(error) };
    }

    return { ok: true };
  } catch (err) {
    return {
      ok: false,
      error: friendlyAuthError({
        message: err instanceof Error ? err.message : "Failed to fetch"
      })
    };
  }
}

export async function sendPasswordReset(email: string): Promise<AuthResult> {
  const normalizedEmail = email.trim().toLowerCase();

  if (!normalizedEmail) {
    return { ok: false, error: "Email is required." };
  }

  const supabase = getSupabaseBrowserClient();

  if (!supabase) {
    return { ok: false, error: missingSupabaseError() };
  }

  try {
    const { error } = await supabase.auth.resetPasswordForEmail(normalizedEmail, {
      redirectTo: `${window.location.origin}/reset-password`
    });

    if (error) {
      return { ok: false, error: friendlyAuthError(error) };
    }
  } catch (err) {
    return {
      ok: false,
      error: friendlyAuthError({
        message: err instanceof Error ? err.message : "Failed to fetch"
      })
    };
  }

  return { ok: true, message: "Password reset email sent. Check your inbox." };
}

export async function updatePassword(password: string): Promise<AuthResult> {
  if (password.length < 6) {
    return { ok: false, error: "Password must be at least 6 characters." };
  }

  const supabase = getSupabaseBrowserClient();

  if (!supabase) {
    return { ok: false, error: missingSupabaseError() };
  }

  const { error } = await supabase.auth.updateUser({ password });

  if (error) {
    return { ok: false, error: error.message };
  }

  return { ok: true, message: "Password updated. You can now log in with your new password." };
}

export async function signOut() {
  const supabase = getSupabaseBrowserClient();

  if (!supabase) {
    return;
  }

  await supabase.auth.signOut();
}

export async function loadFavorites(userId: string): Promise<FavoritesState> {
  const supabase = getSupabaseBrowserClient();

  if (!supabase) {
    return { teamIds: [], players: [] };
  }

  const { data, error } = await supabase
    .from("user_favorites")
    .select("team_ids, players")
    .eq("user_id", userId)
    .maybeSingle<FavoriteRow>();

  if (error || !data) {
    return { teamIds: [], players: [] };
  }

  return {
    teamIds: Array.isArray(data.team_ids) ? data.team_ids : [],
    players: Array.isArray(data.players) ? data.players : []
  };
}

export async function saveFavorites(userId: string, favorites: FavoritesState) {
  const supabase = getSupabaseBrowserClient();

  if (!supabase) {
    return;
  }

  await supabase.from("user_favorites").upsert(
    {
      user_id: userId,
      team_ids: favorites.teamIds,
      players: favorites.players,
      updated_at: new Date().toISOString()
    },
    { onConflict: "user_id" }
  );
}
