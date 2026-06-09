"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode
} from "react";
import {
  FavoritePlayer,
  getSession,
  loadFavorites,
  saveFavorites,
  signIn,
  signOut,
  signUp,
  type AppUser
} from "@/lib/favorites";
import { getSupabaseBrowserClient } from "@/lib/supabase";

type FavoritesContextValue = {
  user: AppUser | null;
  favoriteTeamIds: string[];
  favoritePlayers: FavoritePlayer[];
  isReady: boolean;
  signUp: (email: string, password: string) => Promise<{ ok: true; message?: string } | { ok: false; error: string }>;
  signIn: (email: string, password: string) => Promise<{ ok: true; message?: string } | { ok: false; error: string }>;
  signOut: () => Promise<void>;
  isTeamFavorite: (teamId: string) => boolean;
  toggleTeamFavorite: (teamId: string) => void;
  isPlayerFavorite: (playerId: number) => boolean;
  togglePlayerFavorite: (player: FavoritePlayer) => void;
};

const FavoritesContext = createContext<FavoritesContextValue | null>(null);

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

export function FavoritesProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AppUser | null>(null);
  const [favoriteTeamIds, setFavoriteTeamIds] = useState<string[]>([]);
  const [favoritePlayers, setFavoritePlayers] = useState<FavoritePlayer[]>([]);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    let mounted = true;
    const supabase = getSupabaseBrowserClient();

    async function loadForUser(nextUser: AppUser | null) {
      if (!mounted) {
        return;
      }

      setUser(nextUser);

      if (!nextUser) {
        setFavoriteTeamIds([]);
        setFavoritePlayers([]);
        setIsReady(true);
        return;
      }

      const favorites = await loadFavorites(nextUser.id);

      if (!mounted) {
        return;
      }

      setFavoriteTeamIds(favorites.teamIds);
      setFavoritePlayers(favorites.players);
      setIsReady(true);
    }

    getSession().then(loadForUser);

    const subscription = supabase?.auth.onAuthStateChange((_event, session) => {
      void loadForUser(toAppUser(session?.user ?? null));
    });

    return () => {
      mounted = false;
      subscription?.data.subscription.unsubscribe();
    };
  }, []);

  const persist = useCallback(
    (teamIds: string[], players: FavoritePlayer[]) => {
      if (!user) {
        return;
      }

      void saveFavorites(user.id, { teamIds, players });
    },
    [user]
  );

  const handleSignUp = useCallback(async (email: string, password: string) => {
    const result = await signUp(email, password);

    if (result.ok) {
      const session = await getSession();
      setUser(session);
      setFavoriteTeamIds([]);
      setFavoritePlayers([]);
    }

    return result;
  }, []);

  const handleSignIn = useCallback(async (email: string, password: string) => {
    const result = await signIn(email, password);

    if (result.ok) {
      const session = await getSession();
      setUser(session);

      if (session) {
        const favorites = await loadFavorites(session.id);
        setFavoriteTeamIds(favorites.teamIds);
        setFavoritePlayers(favorites.players);
      }
    }

    return result;
  }, []);

  const handleSignOut = useCallback(async () => {
    await signOut();
    setUser(null);
    setFavoriteTeamIds([]);
    setFavoritePlayers([]);
  }, []);

  const isTeamFavorite = useCallback(
    (teamId: string) => favoriteTeamIds.includes(teamId),
    [favoriteTeamIds]
  );

  const toggleTeamFavorite = useCallback(
    (teamId: string) => {
      if (!user) {
        return;
      }

      setFavoriteTeamIds((current) => {
        const next = current.includes(teamId)
          ? current.filter((id) => id !== teamId)
          : [...current, teamId];
        persist(next, favoritePlayers);
        return next;
      });
    },
    [favoritePlayers, persist, user]
  );

  const isPlayerFavorite = useCallback(
    (playerId: number) => favoritePlayers.some((player) => player.id === playerId),
    [favoritePlayers]
  );

  const togglePlayerFavorite = useCallback(
    (player: FavoritePlayer) => {
      if (!user) {
        return;
      }

      setFavoritePlayers((current) => {
        const next = current.some((item) => item.id === player.id)
          ? current.filter((item) => item.id !== player.id)
          : [...current, player];
        persist(favoriteTeamIds, next);
        return next;
      });
    },
    [favoriteTeamIds, persist, user]
  );

  const value = useMemo(
    () => ({
      user,
      favoriteTeamIds,
      favoritePlayers,
      isReady,
      signUp: handleSignUp,
      signIn: handleSignIn,
      signOut: handleSignOut,
      isTeamFavorite,
      toggleTeamFavorite,
      isPlayerFavorite,
      togglePlayerFavorite
    }),
    [
      favoritePlayers,
      favoriteTeamIds,
      handleSignIn,
      handleSignOut,
      handleSignUp,
      isPlayerFavorite,
      isReady,
      isTeamFavorite,
      togglePlayerFavorite,
      toggleTeamFavorite,
      user
    ]
  );

  return <FavoritesContext.Provider value={value}>{children}</FavoritesContext.Provider>;
}

export function useFavorites() {
  const context = useContext(FavoritesContext);

  if (!context) {
    throw new Error("useFavorites must be used within FavoritesProvider");
  }

  return context;
}
