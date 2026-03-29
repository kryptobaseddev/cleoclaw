"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  Bot,
  Boxes,
  CheckCircle2,
  Folder,
  Building2,
  LayoutGrid,
  Network,
  Settings,
  Store,
  Tags,
} from "lucide-react";

import { useAuth } from "@/auth/session";
import { ApiError } from "@/api/mutator";
import { useOrganizationMembership } from "@/lib/use-organization-membership";
import {
  type healthzHealthzGetResponse,
  useHealthzHealthzGet,
} from "@/api/generated/default/default";
import { cn } from "@/lib/utils";

const navLinkBase =
  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-app-text-muted transition";
const navLinkActive = "bg-app-nav-active text-app-nav-active-text font-medium";
const navLinkIdle = "hover:bg-app-nav-hover";

type NavLinkProps = {
  href: string;
  isActive: boolean;
  icon: React.ReactNode;
  label: string;
};

function NavLink({ href, isActive, icon, label }: NavLinkProps) {
  return (
    <Link
      href={href}
      className={cn(navLinkBase, isActive ? navLinkActive : navLinkIdle)}
    >
      {icon}
      {label}
    </Link>
  );
}

export function DashboardSidebar() {
  const pathname = usePathname();
  const { isSignedIn } = useAuth();
  const { isAdmin } = useOrganizationMembership(isSignedIn);
  const healthQuery = useHealthzHealthzGet<healthzHealthzGetResponse, ApiError>(
    {
      query: {
        refetchInterval: 30_000,
        refetchOnMount: "always",
        retry: false,
      },
      request: { cache: "no-store" },
    },
  );

  const okValue = healthQuery.data?.data?.ok;
  const systemStatus: "unknown" | "operational" | "degraded" =
    okValue === true
      ? "operational"
      : okValue === false
        ? "degraded"
        : healthQuery.isError
          ? "degraded"
          : "unknown";
  const statusLabel =
    systemStatus === "operational"
      ? "All systems operational"
      : systemStatus === "unknown"
        ? "System status unavailable"
        : "System degraded";

  return (
    <aside className="fixed inset-y-0 left-0 z-40 flex w-[280px] -translate-x-full flex-col border-r border-app-border bg-app-surface pt-16 shadow-lg transition-transform duration-200 ease-in-out [[data-sidebar=open]_&]:translate-x-0 md:relative md:inset-auto md:z-auto md:w-[260px] md:translate-x-0 md:pt-0 md:shadow-none md:transition-none">
      <div className="flex-1 px-3 py-4">
        <p className="px-3 text-xs font-semibold uppercase tracking-wider text-app-text-quiet">
          Navigation
        </p>
        <nav className="mt-3 space-y-4 text-sm">
          <div>
            <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-app-text-quiet">
              Overview
            </p>
            <div className="mt-1 space-y-1">
              <NavLink
                href="/dashboard"
                isActive={pathname === "/dashboard"}
                icon={<BarChart3 className="h-4 w-4" />}
                label="Dashboard"
              />
              <NavLink
                href="/activity"
                isActive={pathname.startsWith("/activity")}
                icon={<Activity className="h-4 w-4" />}
                label="Live feed"
              />
            </div>
          </div>

          <div>
            <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-app-text-quiet">
              Boards
            </p>
            <div className="mt-1 space-y-1">
              <NavLink
                href="/board-groups"
                isActive={pathname.startsWith("/board-groups")}
                icon={<Folder className="h-4 w-4" />}
                label="Board groups"
              />
              <NavLink
                href="/boards"
                isActive={pathname.startsWith("/boards")}
                icon={<LayoutGrid className="h-4 w-4" />}
                label="Boards"
              />
              <NavLink
                href="/tags"
                isActive={pathname.startsWith("/tags")}
                icon={<Tags className="h-4 w-4" />}
                label="Tags"
              />
              <NavLink
                href="/approvals"
                isActive={pathname.startsWith("/approvals")}
                icon={<CheckCircle2 className="h-4 w-4" />}
                label="Approvals"
              />
              {isAdmin ? (
                <NavLink
                  href="/custom-fields"
                  isActive={pathname.startsWith("/custom-fields")}
                  icon={<Settings className="h-4 w-4" />}
                  label="Custom fields"
                />
              ) : null}
            </div>
          </div>

          <div>
            {isAdmin ? (
              <>
                <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-app-text-quiet">
                  Skills
                </p>
                <div className="mt-1 space-y-1">
                  <NavLink
                    href="/skills/marketplace"
                    isActive={
                      pathname === "/skills" ||
                      pathname.startsWith("/skills/marketplace")
                    }
                    icon={<Store className="h-4 w-4" />}
                    label="Marketplace"
                  />
                  <NavLink
                    href="/skills/packs"
                    isActive={pathname.startsWith("/skills/packs")}
                    icon={<Boxes className="h-4 w-4" />}
                    label="Packs"
                  />
                </div>
              </>
            ) : null}
          </div>

          <div>
            <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-app-text-quiet">
              Administration
            </p>
            <div className="mt-1 space-y-1">
              <NavLink
                href="/organization"
                isActive={pathname.startsWith("/organization")}
                icon={<Building2 className="h-4 w-4" />}
                label="Organization"
              />
              {isAdmin ? (
                <NavLink
                  href="/gateways"
                  isActive={pathname.startsWith("/gateways")}
                  icon={<Network className="h-4 w-4" />}
                  label="Gateways"
                />
              ) : null}
              {isAdmin ? (
                <NavLink
                  href="/agents"
                  isActive={pathname.startsWith("/agents")}
                  icon={<Bot className="h-4 w-4" />}
                  label="Agents"
                />
              ) : null}
            </div>
          </div>
        </nav>
      </div>
      <div className="border-t border-app-border p-4">
        <div className="flex items-center gap-2 text-xs text-app-text-quiet">
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              systemStatus === "operational" && "bg-emerald-500",
              systemStatus === "degraded" && "bg-rose-500",
              systemStatus === "unknown" && "bg-slate-400",
            )}
          />
          {statusLabel}
        </div>
      </div>
    </aside>
  );
}
