"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Activity } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const setToken = useStore((s) => s.setToken);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await api.login(password);
      setToken(data.access_token);
      router.push("/");
    } catch {
      setError("Invalid password");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="relative w-full max-w-sm">
        {/* Glow behind the card */}
        <div className="absolute -inset-1 rounded-2xl bg-gradient-to-r from-emerald-600/20 via-blue-600/20 to-purple-600/20 blur-xl" />

        <div className="relative rounded-2xl border border-zinc-800 bg-zinc-900/90 p-8 shadow-2xl backdrop-blur-sm">
          <div className="mb-8 flex flex-col items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-600/10 ring-1 ring-emerald-600/30">
              <Activity className="h-6 w-6 text-emerald-400" />
            </div>
            <h1 className="text-xl font-bold text-white">ProjetoCrypto</h1>
            <p className="text-sm text-zinc-500">
              Funding Rate Arbitrage Dashboard
            </p>
          </div>

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label
                htmlFor="password"
                className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-zinc-500"
              >
                Password
              </label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter dashboard password"
                autoFocus
              />
            </div>

            {error && (
              <p className="animate-fade-in text-sm text-red-400">{error}</p>
            )}

            <Button
              type="submit"
              variant="primary"
              className="w-full"
              disabled={loading || !password}
            >
              {loading ? <Spinner className="h-4 w-4" /> : "Sign In"}
            </Button>
          </form>

          <p className="mt-6 text-center text-xs text-zinc-600">
            Secured with JWT authentication
          </p>
        </div>
      </div>
    </div>
  );
}
