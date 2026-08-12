import { NavLink, Outlet } from "react-router";
import { Toaster } from "@/components/ui/sonner";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/chat", label: "Chat" },
  { to: "/orgs", label: "Organizations" },
  { to: "/products", label: "Products" },
  { to: "/graphs", label: "Graphs" },
  { to: "/architecture", label: "Architecture" },
];

export function RootLayout() {
  return (
    <div className="min-h-screen bg-background">
      <div className="flex flex-col">
        <header className="flex h-14 items-center justify-between w-full bg-card border-b border-border px-6 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-primary text-[10px] font-bold text-primary-foreground select-none">
              CS
            </div>
            <span className="text-sm font-semibold text-foreground tracking-tight">
              Chat Simulation
            </span>
          </div>
          <nav className="flex h-full items-stretch">
            {NAV.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to !== "/chat"}
                className={({ isActive }) =>
                  cn(
                    "relative flex h-full items-center px-5 text-sm text-muted-foreground transition-colors hover:text-foreground",
                    isActive &&
                      "font-medium text-primary after:absolute after:inset-x-0 after:-bottom-px after:h-0.5 after:bg-primary",
                  )
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
        </header>
        <main className="flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
      <Toaster />
    </div>
  );
}
