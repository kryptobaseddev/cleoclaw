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
    <main className="flex min-h-screen items-center justify-center bg-slate-950 p-6 text-slate-100">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl"
      >
        <h1 className="mb-1 text-2xl font-semibold">CleoClaw Access</h1>
        <p className="mb-6 text-sm text-slate-400">
          {mode === "signin" ? "Sign in to continue" : "Create your operator account"}
        </p>

        {mode === "signup" ? (
          <input
            type="text"
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mb-3 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2"
            required
          />
        ) : null}

        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mb-3 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2"
          required
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mb-3 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2"
          required
          minLength={8}
        />

        {error ? <p className="mb-3 text-sm text-rose-400">{error}</p> : null}

        <button
          type="submit"
          className="mb-3 w-full rounded-lg bg-sky-500 px-3 py-2 font-medium text-slate-950"
          disabled={loading}
        >
          {loading ? "Please wait..." : mode === "signin" ? "Sign in" : "Create account"}
        </button>

        <button
          type="button"
          className="w-full text-sm text-slate-400 underline"
          onClick={() => setMode((m) => (m === "signin" ? "signup" : "signin"))}
        >
          {mode === "signin" ? "Need an account? Sign up" : "Already have an account? Sign in"}
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
