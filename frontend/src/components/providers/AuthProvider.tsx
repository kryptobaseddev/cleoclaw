"use client";

import { useEffect, type ReactNode } from "react";

import { AuthMode } from "@/auth/mode";
import {
  clearLocalAuthToken,
  getLocalAuthToken,
  setLocalAuthToken,
  isLocalAuthMode,
} from "@/auth/localAuth";
import { LocalAuthLogin } from "@/components/organisms/LocalAuthLogin";
import { authClient } from "@/lib/auth-client";

function BetterAuthSyncToken() {
  const { data, isPending } = authClient.useSession();

  useEffect(() => {
    if (isPending) return;
    if (!data?.session) return;
    const token = process.env.NEXT_PUBLIC_LOCAL_AUTH_TOKEN;
    if (token && token.length >= 50 && !getLocalAuthToken()) {
      setLocalAuthToken(token);
    }
  }, [data, isPending]);

  return null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const mode = process.env.NEXT_PUBLIC_AUTH_MODE;
  const localMode = isLocalAuthMode();

  useEffect(() => {
    if (!localMode && mode !== AuthMode.BetterAuth) {
      clearLocalAuthToken();
    }
  }, [localMode, mode]);

  if (localMode) {
    if (!getLocalAuthToken()) {
      return <LocalAuthLogin />;
    }
    return <>{children}</>;
  }

  if (mode === AuthMode.BetterAuth) {
    return (
      <>
        <BetterAuthSyncToken />
        {children}
      </>
    );
  }

  return <>{children}</>;
}
