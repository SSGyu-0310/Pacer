"use client";

import type React from "react";
import { useState } from "react";

export default function AdminLoginPage() {
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const res = await fetch("/api/admin/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ token }),
    });
    if (!res.ok) {
      setError("토큰을 확인해 주세요.");
      return;
    }
    window.location.href = "/admin/review";
  }

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-10 text-white">
      <form onSubmit={submit} className="mx-auto mt-24 flex w-full max-w-sm flex-col gap-3">
        <h1 className="text-xl font-semibold">Pacer Admin</h1>
        <input
          type="password"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-cyan-400"
          placeholder="ADMIN_TOKEN"
        />
        <button className="rounded-lg bg-cyan-400 px-3 py-2 text-sm font-semibold text-slate-950">
          로그인
        </button>
        {error ? <p className="text-sm text-rose-300">{error}</p> : null}
      </form>
    </main>
  );
}
