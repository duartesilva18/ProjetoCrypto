import type {
  BotEvent,
  BotStatus,
  EquityPoint,
  FundingRateEntry,
  LoginResponse,
  PnlSummary,
  Position,
} from "@/types/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function headers(): HeadersInit {
  const h: HeadersInit = { "Content-Type": "application/json" };
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("token");
    if (token) h["Authorization"] = `Bearer ${token}`;
  }
  return h;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: headers(),
    ...init,
  });
  if (res.status === 401) {
    if (typeof window !== "undefined") {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    throw new Error("Unauthorized");
  }
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  login: (password: string) =>
    request<LoginResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

  getFundingRates: () =>
    request<{ rates: Record<string, FundingRateEntry>; count: number }>(
      "/api/v1/funding/rates"
    ),

  getPositions: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return request<{ total: number; data: Position[] }>(
      `/api/v1/positions${qs}`
    );
  },

  getPosition: (id: string) =>
    request<{
      position: Position;
      funding_payments: { timestamp: string; payment: number; rate: number }[];
    }>(`/api/v1/positions/${id}`),

  getPnl: () => request<PnlSummary>("/api/v1/metrics/pnl"),

  getEquityCurve: (hours = 24) =>
    request<{ data: EquityPoint[] }>(`/api/v1/metrics/equity?hours=${hours}`),

  getBotStatus: () =>
    request<{ status: BotStatus }>("/api/v1/bot/status"),

  startBot: () =>
    request<{ message: string }>("/api/v1/bot/start", { method: "POST" }),

  stopBot: () =>
    request<{ message: string }>("/api/v1/bot/stop", { method: "POST" }),

  emergencyStop: () =>
    request<{ message: string }>("/api/v1/bot/emergency-stop", {
      method: "POST",
    }),

  getEvents: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return request<{ count: number; data: BotEvent[] }>(
      `/api/v1/events${qs}`
    );
  },
};
