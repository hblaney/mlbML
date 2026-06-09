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
  type LocalUser
} from "@/lib/favorites";

type FavoritesContextValue = {
  user: LocalUser | null;
  favoriteTeamIds: string[];
  favoritePlayers: FavoritePlayer[];
  isReady: boolean;
  signUp: (email: string, password: string) => { ok: true } | { ok: false; error: string };
  signIn: (email: string, password: string) => { ok: true } | { ok: false; error: string };
  signOut: () => void;
  isTeamFavorite: (teamId: string) => boolean;
  toggleTeamFavorite: (teamId: string) => void;
  isPlayerFavorite: (playerId: number) => boolean;
  togglePlayerFavorite: (player: FavoritePlayer) => void;
};

const FavoritesContext = createContext<FavoritesContextValue | null>(null);

export function FavoritesProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<LocalUser | null>(null);
  const [favoriteTeamIds, setFavoriteTeamIds] = useState<string[]>([]);
  const [favoritePlayers, setFavoritePlayers] = useState<FavoritePlayer[]>([]);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    const session = getSession();
    setUser(session);

    if (session) {
      const favorites = loadFavorites(session.email);
      setFavoriteTeamIds(favorites.teamIds);
      setFavoritePlayers(favorites.players);
    }

    setIsReady(true);
  }, []);

  const persist = useCallback(
    (teamIds: string[], players: FavoritePlayer[]) => {
      if (!user) {
        return;
      }

      saveFavorites(user.email, { teamIds, players });
    },
    [user]
  );

  const handleSignUp = useCallback((email: string, password: string) => {
    const result = signUp(email, password);

    if (result.ok) {
      const session = getSession();
      setUser(session);
      setFavoriteTeamIds([]);
      setFavoritePlayers([]);
    }

    return result;
  }, []);

  const handleSignIn = useCallback((email: string, password: string) => {
    const result = signIn(email, password);

    if (result.ok) {
      const session = getSession();
      setUser(session);

      if (session) {
        const favorites = loadFavorites(session.email);
        setFavoriteTeamIds(favorites.teamIds);
        setFavoritePlayers(favorites.players);
      }
    }

    return result;
  }, []);

  const handleSignOut = useCallback(() => {
    signOut();
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
