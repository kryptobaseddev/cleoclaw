"use client";

import Link from "next/link";
import type { ReactElement, ReactNode } from "react";

import { AuthMode } from "@/auth/mode";
import { clearLocalAuthToken, getLocalAuthToken, isLocalAuthMode } from "@/auth/localAuth";
import { authClient } from "@/lib/auth-client";

function isBetterAuthMode(): boolean {
  return process.env.NEXT_PUBLIC_AUTH_MODE === AuthMode.BetterAuth;
}

function hasLocalAuthToken(): boolean {
  return Boolean(getLocalAuthToken());
}

export function isAuthEnabled(): boolean {
  return isBetterAuthMode();
}

export function SignedIn(props: { children: ReactNode }) {
  if (isLocalAuthMode()) {
    return hasLocalAuthToken() ? <>{props.children}</> : null;
  }
  if (isBetterAuthMode()) {
    const { data, isPending } = authClient.useSession();
    if (isPending) return null;
    return data?.session ? <>{props.children}</> : null;
  }
  return null;
}

export function SignedOut(props: { children: ReactNode }) {
  if (isLocalAuthMode()) {
    return hasLocalAuthToken() ? null : <>{props.children}</>;
  }
  if (isBetterAuthMode()) {
    const { data, isPending } = authClient.useSession();
    if (isPending) return null;
    return data?.session ? null : <>{props.children}</>;
  }
  return <>{props.children}</>;
}

type SignInButtonProps = {
  children: ReactElement;
  mode?: "modal" | "redirect";
  forceRedirectUrl?: string;
  signUpForceRedirectUrl?: string;
};

export function SignInButton({ children, forceRedirectUrl }: SignInButtonProps) {
  if (isLocalAuthMode()) return null;
  const target = forceRedirectUrl
    ? `/sign-in?redirect_url=${encodeURIComponent(forceRedirectUrl)}`
    : "/sign-in";
  return <Link href={target}>{children}</Link>;
}

export function SignOutButton(props: { children: ReactNode }) {
  const handleSignOut = async () => {
    try {
      await authClient.signOut();
    } catch {
      // ignore
    }
    clearLocalAuthToken();
    window.location.reload();
  };

  return (
    <span
      onClick={() => {
        void handleSignOut();
      }}
    >
      {props.children}
    </span>
  );
}

export function useUser() {
  if (isLocalAuthMode()) {
    return { isLoaded: true, isSignedIn: hasLocalAuthToken(), user: null } as const;
  }
  const { data, isPending } = authClient.useSession();
  return {
    isLoaded: !isPending,
    isSignedIn: Boolean(data?.session),
    user: data?.user
      ? {
          id: data.user.id,
          imageUrl: data.user.image,
          fullName: data.user.name ?? null,
          firstName: data.user.name?.split(" ")[0] ?? null,
          username: data.user.email?.split("@")[0] ?? null,
          primaryEmailAddress: data.user.email
            ? { emailAddress: data.user.email }
            : null,
          emailAddresses: data.user.email ? [{ emailAddress: data.user.email }] : [],
        }
      : null,
  } as const;
}

export function useAuth() {
  if (isLocalAuthMode()) {
    const token = getLocalAuthToken();
    return {
      isLoaded: true,
      isSignedIn: Boolean(token),
      userId: token ? "local-user" : null,
      sessionId: token ? "local-session" : null,
      getToken: async () => token,
    } as const;
  }
  const { data, isPending } = authClient.useSession();
  return {
    isLoaded: !isPending,
    isSignedIn: Boolean(data?.session),
    userId: data?.user?.id ?? null,
    sessionId: data?.session?.id ?? null,
    getToken: async () => null,
  } as const;
}

export const SessionProvider = ({ children }: { children: ReactNode }) => <>{children}</>;
