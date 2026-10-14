"use client";

import { useActionState } from "react";

import { login, type LoginState } from "@/actions/auth";

const INITIAL: LoginState = {};

export default function LoginPage() {
  const [state, formAction, pending] = useActionState(login, INITIAL);

  return (
    <main className="flex min-h-dvh items-center justify-center px-4">
      <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-ink-900/55 p-7 shadow-[0_8px_30px_rgba(0,0,0,0.35)] backdrop-blur-xl">
        <div className="mb-6 flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-500/15 text-lg font-bold text-accent-300">
            S
          </span>
          <div>
            <h1 className="text-base font-semibold text-mist-100">Synpo GTM Console</h1>
            <p className="font-mono text-[11px] text-mist-400">restricted access</p>
          </div>
        </div>

        <form action={formAction} className="space-y-3">
          <label htmlFor="password" className="block text-[11px] font-semibold uppercase tracking-widest text-mist-400">
            Access password
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            className="field"
            placeholder="••••••••"
          />
          <button
            type="submit"
            disabled={pending}
            className="w-full rounded-lg bg-accent-500 px-4 py-2 text-sm font-semibold text-ink-950 transition-colors hover:bg-accent-400 disabled:opacity-50"
          >
            {pending ? "Checking…" : "Enter console"}
          </button>
          {state.error ? <p className="text-xs text-rose-alert">{state.error}</p> : null}
        </form>
      </div>
    </main>
  );
}
