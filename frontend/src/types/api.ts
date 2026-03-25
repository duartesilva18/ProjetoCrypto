export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface FundingRateEntry {
  exchange: string;
  symbol: string;
  funding_rate: string;
  predicted_rate: string;
  mark_price: string;
  index_price: string;
  next_funding_time: string;
  time_to_funding_s: string;
  ts: string;
}

export interface Position {
  id: string;
  exchange: string;
  symbol: string;
  side: string;
  strategy?: string;
  spot_qty: number;
  perp_qty: number;
  entry_price_spot: number;
  entry_price_perp: number;
  status: string;
  funding_collected: number;
  opened_at: string | null;
  closed_at: string | null;
  is_paper: boolean;
  grid_low?: number;
  grid_high?: number;
  levels?: number;
  trades_completed?: number;
  entry_premium_bps?: number;
  current_premium_bps?: number;
}

export interface PnlSummary {
  funding_pnl: {
    daily: number;
    weekly: number;
    monthly: number;
    all_time: number;
  };
  positions: {
    open: number;
    closed: number;
  };
}

export interface EquityPoint {
  timestamp: string;
  total_equity: number;
  unrealized_pnl: number;
  realized_pnl: number;
  funding_pnl: number;
  positions_count: number;
}

export interface BotStatus {
  status: string;
  [key: string]: string;
}

export interface BotEvent {
  id: string;
  timestamp: string;
  level: string;
  component: string;
  message: string;
  metadata: Record<string, unknown> | null;
}

export interface AnalyticsPoint {
  period: string;
  funding_arb: number;
  grid: number;
  carry: number;
  total: number;
}

export interface AnalyticsResponse {
  period: string;
  days: number;
  strategies: string[];
  summary: Record<string, number>;
  data: AnalyticsPoint[];
}
