"use client";

import Link from "next/link";
import { useFavorites } from "@/components/FavoritesProvider";
import type { FavoritePlayer } from "@/lib/favorites";

type FavoriteButtonProps =
  | {
      kind: "team";
      teamId: string;
      label?: string;
    }
  | {
      kind: "player";
      player: FavoritePlayer;
      label?: string;
    };

export function FavoriteButton(props: FavoriteButtonProps) {
  const { user, isTeamFavorite, toggleTeamFavorite, isPlayerFavorite, togglePlayerFavorite } = useFavorites();

  if (!user) {
    return (
      <Link className="favorite-button muted" href="/login" title="Log in to save favorites">
        ☆
      </Link>
    );
  }

  if (props.kind === "team") {
    const active = isTeamFavorite(props.teamId);

    return (
      <button
        aria-label={active ? `Remove ${props.label ?? props.teamId} from favorites` : `Add ${props.label ?? props.teamId} to favorites`}
        className={active ? "favorite-button active" : "favorite-button"}
        onClick={() => toggleTeamFavorite(props.teamId)}
        type="button"
      >
        {active ? "★" : "☆"}
      </button>
    );
  }

  const active = isPlayerFavorite(props.player.id);

  return (
    <button
      aria-label={active ? `Remove ${props.player.name} from favorites` : `Add ${props.player.name} to favorites`}
      className={active ? "favorite-button active" : "favorite-button"}
      onClick={() => togglePlayerFavorite(props.player)}
      type="button"
    >
      {active ? "★" : "☆"}
    </button>
  );
}
