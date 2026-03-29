"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { AuthMode } from "@/auth/mode";
import { isLocalAuthMode } from "@/auth/localAuth";
import { setLocalAuthToken } from "@/auth/localAuth";
import { resolveSignInRedirectUrl } from "@/auth/redirects";
import { LocalAuthLogin } from "@/components/organisms/LocalAuthLogin";
import { authClient } from "@/lib/auth-client";

function BetterAuthSignInForm({ redirectTo }: { redirectTo: string }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (mode === "signup") {
        await authClient.signUp.email({ name: name || "Operator", email, password });
      } else {
        await authClient.signIn.email({ email, password });
      }
      const token = process.env.NEXT_PUBLIC_LOCAL_AUTH_TOKEN;
      if (token && token.length >= 50) {
        setLocalAuthToken(token);
      }
      window.location.href = redirectTo;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main
      className="flex min-h-screen items-center justify-center bg-app-bg p-6 text-app-text"
      style={{
        backgroundImage:
          "linear-gradient(rgba(61,73,76,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(61,73,76,0.05) 1px, transparent 1px)",
        backgroundSize: "40px 40px",
      }}
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md rounded-2xl border border-app-border bg-app-surface/95 backdrop-blur-glass p-8 shadow-panel"
        style={{ boxShadow: "0 0 40px rgba(47, 217, 244, 0.03)" }}
      >
        <h1 className="mb-1 font-display text-2xl italic text-app-accent">
          CleoClaw Access
        </h1>
        <p className="mb-6 font-label text-[10px] uppercase tracking-[0.15em] text-app-text-quiet">
          {mode === "signin" ? "Neural Authentication" : "Operator Registration"}
        </p>

        {mode === "signup" ? (
          <input
            type="text"
            placeholder="Operator Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mb-3 w-full rounded-lg border-b border-app-border border-t-0 border-l-0 border-r-0 bg-app-surface-muted px-4 py-3 text-sm text-app-text placeholder:text-app-text-quiet focus:border-b-app-accent focus:shadow-[0_1px_0_0_var(--accent)] focus:outline-none"
            required
          />
        ) : null}

        <input
          type="email"
          placeholder="Access ID / Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mb-3 w-full rounded-lg border-b border-app-border border-t-0 border-l-0 border-r-0 bg-app-surface-muted px-4 py-3 text-sm text-app-text placeholder:text-app-text-quiet focus:border-b-app-accent focus:shadow-[0_1px_0_0_var(--accent)] focus:outline-none"
          required
        />
        <input
          type="password"
          placeholder="Neural Key / Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mb-3 w-full rounded-lg border-b border-app-border border-t-0 border-l-0 border-r-0 bg-app-surface-muted px-4 py-3 text-sm text-app-text placeholder:text-app-text-quiet focus:border-b-app-accent focus:shadow-[0_1px_0_0_var(--accent)] focus:outline-none"
          required
          minLength={8}
        />

        {error ? (
          <p className="mb-3 text-sm text-app-danger">{error}</p>
        ) : null}

        <button
          type="submit"
          className="mb-4 w-full rounded-xl bg-gradient-to-r from-[#2fd9f4] to-[#06b6d4] px-4 py-3 font-semibold text-white shadow-sm transition-shadow hover:shadow-glow disabled:opacity-50"
          disabled={loading}
        >
          {loading
            ? "Initiating link..."
            : mode === "signin"
              ? "Initiate Link"
              : "Register Operator"}
        </button>

        <button
          type="button"
          className="w-full text-sm text-app-text-quiet transition-colors hover:text-app-accent"
          onClick={() => setMode((m) => (m === "signin" ? "signup" : "signin"))}
        >
          {mode === "signin"
            ? "Need an account? Sign up"
            : "Already have an account? Sign in"}
        </button>
      </form>
    </main>
  );
}

export default function SignInPage() {
  const searchParams = useSearchParams();

  if (isLocalAuthMode()) {
    return <LocalAuthLogin />;
  }

  const forceRedirectUrl = resolveSignInRedirectUrl(
    searchParams.get("redirect_url"),
  );

  if (process.env.NEXT_PUBLIC_AUTH_MODE === AuthMode.BetterAuth) {
    return <BetterAuthSignInForm redirectTo={forceRedirectUrl} />;
  }

  return <LocalAuthLogin />;
}
