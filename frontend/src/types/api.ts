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
  spot_qty: number;
  perp_qty: number;
  entry_price_spot: number;
  entry_price_perp: number;
  status: string;
  funding_collected: number;
  opened_at: string | null;
  closed_at: string | null;
  is_paper: boolean;
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
