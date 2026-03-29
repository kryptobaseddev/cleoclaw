import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import ActivityPage from "./page";
import { AuthProvider } from "@/components/providers/AuthProvider";
import { QueryProvider } from "@/components/providers/QueryProvider";

vi.mock("next/navigation", () => ({
  usePathname: () => "/activity",
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
  }),
}));

vi.mock("next/link", () => {
  type LinkProps = React.PropsWithChildren<{
    href: string | { pathname?: string };
  }> &
    Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "href">;

  return {
    default: ({ href, children, ...props }: LinkProps) => (
      <a href={typeof href === "string" ? href : "#"} {...props}>
        {children}
      </a>
    ),
  };
});

// Guard against accidental dependency on legacy auth providers in local mode.
vi.mock("@/auth/session", () => {
  return {
    SignedIn: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    SignedOut: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    SignInButton: ({ children }: { children: React.ReactNode }) => (
      <>{children}</>
    ),
    SignOutButton: ({ children }: { children: React.ReactNode }) => (
      <>{children}</>
    ),
    useAuth: () => ({ isLoaded: true, isSignedIn: false }),
    useUser: () => ({ isLoaded: true, isSignedIn: false, user: null }),
  };
});

describe("/activity auth boundary", () => {
  it("renders local auth boundary without legacy provider wiring", () => {
    const previousAuthMode = process.env.NEXT_PUBLIC_AUTH_MODE;
    const previousBetterAuthUrl = process.env.NEXT_PUBLIC_BETTER_AUTH_URL;

    process.env.NEXT_PUBLIC_AUTH_MODE = "local";
    process.env.NEXT_PUBLIC_BETTER_AUTH_URL = "http://localhost:3010";
    window.sessionStorage.clear();

    try {
      render(
        <AuthProvider>
          <QueryProvider>
            <ActivityPage />
          </QueryProvider>
        </AuthProvider>,
      );

      expect(
        screen.getByRole("heading", { name: /local authentication/i }),
      ).toBeInTheDocument();
      expect(screen.getByLabelText(/access token/i)).toBeInTheDocument();
    } finally {
      process.env.NEXT_PUBLIC_AUTH_MODE = previousAuthMode;
      process.env.NEXT_PUBLIC_BETTER_AUTH_URL = previousBetterAuthUrl;
      window.sessionStorage.clear();
    }
  });
});
