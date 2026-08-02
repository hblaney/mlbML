"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useFavorites } from "@/components/FavoritesProvider";

const primary = [
  { href: "/", label: "Board" },
  { href: "/props", label: "Props" },
  { href: "/best-bets", label: "Moneyline" },
  { href: "/accuracy", label: "Accuracy" },
];

const more = [
  { href: "/watch", label: "Watch" },
  { href: "/stats", label: "Stats" },
  { href: "/bet-watcher", label: "Bet Watcher" },
  { href: "/paper-trading", label: "Paper Bets" },
  { href: "/favorites", label: "Favorites" },
];

export function Nav() {
  const { user, signOut } = useFavorites();
  const pathname = usePathname();

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);

  return (
    <header className="site-header">
      <nav className="nav shell">
        <Link className="brand" href="/">
          <span className="brand-mark">ME</span>
          <span className="brand-text">
            MLB Edge
            <span>daily board</span>
          </span>
        </Link>

        <div className="nav-trail">
          <div className="links primary-links">
            {primary.map((link) => (
              <Link
                href={link.href}
                key={link.href}
                className={isActive(link.href) ? "active" : undefined}
              >
                {link.label}
              </Link>
            ))}
          </div>

          <details className="nav-more">
            <summary>More</summary>
            <div className="nav-more-menu">
              {more.map((link) => (
                <Link href={link.href} key={link.href}>
                  {link.label}
                </Link>
              ))}
              {user ? (
                <button className="text-button" onClick={() => void signOut()} type="button">
                  Log out ({user.email?.split("@")[0]})
                </button>
              ) : (
                <Link href="/login">Log in</Link>
              )}
            </div>
          </details>
        </div>
      </nav>
    </header>
  );
}
