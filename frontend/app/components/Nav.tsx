"use client";

import { Footprints } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "../lib/theme";

// The app's only three top-level pages. Shown on every page so navigation is
// always available.
const LINKS: ReadonlyArray<readonly [string, string]> = [
  ["/", "Map"],
  ["/status", "Reports"],
  ["/about", "About"]
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  // The report-submission flow (/report) belongs to the Reports tab.
  if (href === "/status") return pathname.startsWith("/status") || pathname.startsWith("/report");
  return pathname.startsWith(href);
}

export default function Nav() {
  const pathname = usePathname() ?? "/";
  const { theme, toggle } = useTheme();

  return (
    <nav className="nav">
      <div className="brand">
        <span><Footprints size={21} /></span>
        Safewalk
      </div>
      <div className="nav-links">
        {LINKS.map(([href, label]) => (
          <Link key={href} className={isActive(pathname, href) ? "active" : ""} href={href}>
            {label}
          </Link>
        ))}
      </div>
      <button
        className={`theme-toggle ${theme === "dark" ? "is-dark" : ""}`}
        onClick={toggle}
        type="button"
      >
        <svg
          aria-hidden="true"
          className="theme-toggle-icon"
          fill="currentColor"
          strokeLinecap="round"
          viewBox="0 0 32 32"
        >
          <g>
            <circle className="theme-toggle-core" cx="16" cy="16" />
            <circle className="theme-toggle-cutout" cx="21" cy="11" r="8" />
            <g className="theme-toggle-rays" stroke="currentColor" strokeWidth="1.5">
              <path d="M16 5.5v-4" />
              <path d="M16 30.5v-4" />
              <path d="M1.5 16h4" />
              <path d="M26.5 16h4" />
              <path d="m23.4 8.6 2.8-2.8" />
              <path d="m5.7 26.3 2.9-2.9" />
              <path d="m5.8 5.8 2.8 2.8" />
              <path d="m23.4 23.4 2.9 2.9" />
            </g>
          </g>
        </svg>
        {theme === "dark" ? "Light" : "Dark"}
      </button>
    </nav>
  );
}
