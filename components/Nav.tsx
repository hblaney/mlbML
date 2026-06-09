"use client";

import Link from "next/link";
import { useFavorites } from "@/components/FavoritesProvider";

const links = [
  { href: "/", label: "Home" },
  { href: "/best-bets", label: "Best Bets" },
  { href: "/stats", label: "Stats" },
  { href: "/history", label: "Accuracy" },
  { href: "/watch", label: "Watch" },
  { href: "/favorites", label: "Favorites" }
];

export function Nav() {
  const { user, signOut } = useFavorites();

  return (
    <header>
      <div className="topline">
        <div className="shell topline-inner">
          <span>MLB market board</span>
          <span>Daily model refresh</span>
          <span>Real odds only</span>
        </div>
      </div>
      <nav className="nav shell">
        <Link className="brand" href="/">
          <span className="brand-mark">ME</span>
          <span className="brand-text">
            MLB Edge
            <span>model driven baseball</span>
          </span>
        </Link>
        <div className="links">
          {links.map((link) => (
            <Link href={link.href} key={link.href}>
              {link.label}
            </Link>
          ))}
          {user ? (
            <>
              <span className="nav-user muted">{user.email}</span>
              <button className="button" onClick={() => void signOut()} type="button">
                Log out
              </button>
            </>
          ) : (
            <Link className="button" href="/login">
              Log in
            </Link>
          )}
        </div>
      </nav>
    </header>
  );
}
