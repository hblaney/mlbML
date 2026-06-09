import Link from "next/link";

const links = [
  { href: "/", label: "Home" },
  { href: "/best-bets", label: "Best Bets" },
  { href: "/history", label: "History" },
  { href: "/stats", label: "Stats" },
  { href: "/watch", label: "Watch" },
  { href: "/accuracy", label: "Accuracy" },
  { href: "/dashboard", label: "My Teams" }
];

export function Nav() {
  return (
    <nav className="nav shell">
      <Link className="brand" href="/">
        MLB Edge
        <span>model driven baseball</span>
      </Link>
      <div className="links">
        {links.map((link) => (
          <Link href={link.href} key={link.href}>
            {link.label}
          </Link>
        ))}
        <Link className="button" href="/login">
          Log in
        </Link>
      </div>
    </nav>
  );
}
