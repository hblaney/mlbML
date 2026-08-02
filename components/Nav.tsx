"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { useFavorites } from "@/components/FavoritesProvider";

const primary = [
  { href: "/", label: "Board" },
  { href: "/props", label: "Props" },
  { href: "/best-bets", label: "Moneyline" },
  { href: "/watch", label: "Watch" },
  { href: "/accuracy", label: "Accuracy" },
];

const more = [
  { href: "/stats", label: "Stats" },
  { href: "/bet-watcher", label: "Bet Watcher" },
  { href: "/paper-trading", label: "Paper Bets" },
  { href: "/favorites", label: "Favorites" },
];

export function Nav() {
  const { user, signOut } = useFavorites();
  const pathname = usePathname();
  const moreRef = useRef<HTMLDetailsElement>(null);

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);

  const closeMore = () => {
    if (moreRef.current) moreRef.current.open = false;
  };

  useEffect(() => {
    closeMore();
  }, [pathname]);

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      const el = moreRef.current;
      if (!el?.open) return;
      if (!el.contains(event.target as Node)) {
        el.open = false;
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeMore();
    };

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

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

          <details ref={moreRef} className="nav-more">
            <summary>More</summary>
            <div className="nav-more-menu">
              {more.map((link) => (
                <Link href={link.href} key={link.href} onClick={closeMore}>
                  {link.label}
                </Link>
              ))}
              {user ? (
                <button
                  className="text-button"
                  onClick={() => {
                    closeMore();
                    void signOut();
                  }}
                  type="button"
                >
                  Log out ({user.email?.split("@")[0]})
                </button>
              ) : (
                <Link href="/login" onClick={closeMore}>
                  Log in
                </Link>
              )}
            </div>
          </details>
        </div>
      </nav>
    </header>
  );
}
