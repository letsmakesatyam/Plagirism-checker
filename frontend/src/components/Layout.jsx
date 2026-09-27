import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const facultyLinks = [
  { to: "/faculty/dashboard", label: "Dashboard" },
  { to: "/faculty/assignments", label: "Assignments" },
  { to: "/faculty/reports", label: "Reports" },
  { to: "/faculty/sources", label: "Source Library" },
];

const studentLinks = [
  { to: "/student/dashboard", label: "Dashboard" },
  { to: "/student/assignments", label: "Assignments" },
  { to: "/student/submissions", label: "My Submissions" },
];

function Brand() {
  return (
    <div className="flex items-center gap-2">
      <span className="h-8 w-8 rounded-seal border-2 border-brass flex items-center justify-center font-display text-brass text-sm shrink-0">
        O
      </span>
      <div>
        <p className="font-display text-lg leading-none text-ink">Originum</p>
        <p className="text-[10px] font-mono uppercase tracking-wide text-slate-light">Integrity Checker</p>
      </div>
    </div>
  );
}

function SidebarContent({ links, user, logout, onNavigate }) {
  return (
    <>
      <div className="px-5 py-6 border-b border-line">
        <Brand />
      </div>
      <nav className="flex-1 px-3 py-5 space-y-1 overflow-y-auto">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            onClick={onNavigate}
            className={({ isActive }) =>
              `block px-3 py-2 rounded-sm text-sm font-medium transition-colors ${
                isActive ? "bg-forest text-paper" : "text-slate hover:bg-black/5 hover:text-ink"
              }`
            }
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
      <div className="px-3 py-4 border-t border-line">
        <div className="px-3 mb-2">
          <p className="text-sm text-ink font-medium truncate">{user?.full_name}</p>
          <p className="text-xs text-slate-light font-mono truncate">{user?.email}</p>
        </div>
        <button onClick={logout} className="btn-ghost w-full justify-start text-sm">
          Sign out
        </button>
      </div>
    </>
  );
}

export default function Layout() {
  const { user, logout, isFaculty } = useAuth();
  const links = isFaculty ? facultyLinks : studentLinks;
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-screen lg:flex">
      {/* Mobile top bar */}
      <div className="lg:hidden sticky top-0 z-30 flex items-center justify-between border-b border-line bg-white px-4 py-3">
        <Brand />
        <button
          type="button"
          aria-label="Open menu"
          onClick={() => setMobileOpen(true)}
          className="btn-ghost px-2 py-2"
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
      </div>

      {/* Mobile off-canvas drawer */}
      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-40 flex">
          <div className="absolute inset-0 bg-ink/40" onClick={() => setMobileOpen(false)} />
          <aside className="relative z-50 w-72 max-w-[80vw] bg-white flex flex-col shadow-xl">
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => setMobileOpen(false)}
              className="absolute top-4 right-3 btn-ghost px-2 py-1"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
            <SidebarContent links={links} user={user} logout={logout} onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      {/* Desktop sidebar */}
      <aside className="hidden lg:flex w-60 shrink-0 border-r border-line bg-white flex-col">
        <SidebarContent links={links} user={user} logout={logout} />
      </aside>

      <main className="flex-1 min-w-0">
        <div className="max-w-6xl mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
