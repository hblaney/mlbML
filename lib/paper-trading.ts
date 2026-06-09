import { getSupabaseBrowserClient } from "@/lib/supabase";

export type PaperBetStatus = "open" | "won" | "lost" | "void";

export type PaperAccount = {
  userId: string;
  startingBalance: number;
  balance: number;
  updatedAt: string;
};

export type PaperBet = {
  id: string;
  userId: string;
  gameId: string;
  startsAt: string;
  matchup: string;
  teamId: string;
  teamName: string;
  opponentId: string;
  opponentName: string;
  side: string;
  odds: number;
  stake: number;
  potentialProfit: number;
  modelProbability: number | null;
  bookProbability: number | null;
  edge: number | null;
  status: PaperBetStatus;
  settledProfit: number | null;
  placedAt: string;
  settledAt: string | null;
};

export type PaperBetInput = Omit<PaperBet, "id" | "userId" | "status" | "settledProfit" | "placedAt" | "settledAt">;

type PaperAccountRow = {
  user_id: string;
  starting_balance: number | string;
  balance: number | string;
  updated_at: string;
};

type PaperBetRow = {
  id: string;
  user_id: string;
  game_id: string;
  starts_at: string;
  matchup: string;
  team_id: string;
  team_name: string;
  opponent_id: string;
  opponent_name: string;
  side: string;
  odds: number;
  stake: number | string;
  potential_profit: number | string;
  model_probability: number | string | null;
  book_probability: number | string | null;
  edge: number | string | null;
  status: PaperBetStatus;
  settled_profit: number | string | null;
  placed_at: string;
  settled_at: string | null;
};

const DEFAULT_BALANCE = 10000;

function toNumber(value: number | string | null, fallback = 0) {
  if (value === null) {
    return fallback;
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function toAccount(row: PaperAccountRow): PaperAccount {
  return {
    userId: row.user_id,
    startingBalance: toNumber(row.starting_balance, DEFAULT_BALANCE),
    balance: toNumber(row.balance, DEFAULT_BALANCE),
    updatedAt: row.updated_at
  };
}

function toBet(row: PaperBetRow): PaperBet {
  return {
    id: row.id,
    userId: row.user_id,
    gameId: row.game_id,
    startsAt: row.starts_at,
    matchup: row.matchup,
    teamId: row.team_id,
    teamName: row.team_name,
    opponentId: row.opponent_id,
    opponentName: row.opponent_name,
    side: row.side,
    odds: row.odds,
    stake: toNumber(row.stake),
    potentialProfit: toNumber(row.potential_profit),
    modelProbability: row.model_probability === null ? null : toNumber(row.model_probability),
    bookProbability: row.book_probability === null ? null : toNumber(row.book_probability),
    edge: row.edge === null ? null : toNumber(row.edge),
    status: row.status,
    settledProfit: row.settled_profit === null ? null : toNumber(row.settled_profit),
    placedAt: row.placed_at,
    settledAt: row.settled_at
  };
}

function missingSupabaseError() {
  return "Supabase is not configured yet. Add NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in Vercel.";
}

export function paperProfitForOdds(odds: number, stake: number) {
  return odds > 0 ? (odds / 100) * stake : (100 / Math.abs(odds)) * stake;
}

export async function loadPaperTrading(userId: string): Promise<{ account: PaperAccount; bets: PaperBet[] }> {
  const supabase = getSupabaseBrowserClient();

  if (!supabase) {
    throw new Error(missingSupabaseError());
  }

  const { data: accountRow, error: accountError } = await supabase
    .from("paper_trading_accounts")
    .select("user_id, starting_balance, balance, updated_at")
    .eq("user_id", userId)
    .maybeSingle<PaperAccountRow>();

  if (accountError) {
    throw new Error(accountError.message);
  }

  const account = accountRow
    ? toAccount(accountRow)
    : await resetPaperAccount(userId, DEFAULT_BALANCE);

  const { data: betRows, error: betsError } = await supabase
    .from("paper_trading_bets")
    .select("*")
    .eq("user_id", userId)
    .order("placed_at", { ascending: false })
    .returns<PaperBetRow[]>();

  if (betsError) {
    throw new Error(betsError.message);
  }

  return {
    account,
    bets: (betRows ?? []).map(toBet)
  };
}

export async function resetPaperAccount(userId: string, balance = DEFAULT_BALANCE): Promise<PaperAccount> {
  const supabase = getSupabaseBrowserClient();

  if (!supabase) {
    throw new Error(missingSupabaseError());
  }

  const { data, error } = await supabase
    .from("paper_trading_accounts")
    .upsert(
      {
        user_id: userId,
        starting_balance: balance,
        balance,
        updated_at: new Date().toISOString()
      },
      { onConflict: "user_id" }
    )
    .select("user_id, starting_balance, balance, updated_at")
    .single<PaperAccountRow>();

  if (error) {
    throw new Error(error.message);
  }

  await supabase.from("paper_trading_bets").delete().eq("user_id", userId);
  return toAccount(data);
}

export async function placePaperBet(userId: string, currentBalance: number, input: PaperBetInput): Promise<void> {
  const supabase = getSupabaseBrowserClient();

  if (!supabase) {
    throw new Error(missingSupabaseError());
  }

  if (input.stake <= 0) {
    throw new Error("Stake must be greater than zero.");
  }

  if (input.stake > currentBalance) {
    throw new Error("You do not have enough paper balance for that stake.");
  }

  const nextBalance = currentBalance - input.stake;
  const now = new Date().toISOString();

  const { error: betError } = await supabase.from("paper_trading_bets").insert({
    user_id: userId,
    game_id: input.gameId,
    starts_at: input.startsAt,
    matchup: input.matchup,
    team_id: input.teamId,
    team_name: input.teamName,
    opponent_id: input.opponentId,
    opponent_name: input.opponentName,
    side: input.side,
    odds: input.odds,
    stake: input.stake,
    potential_profit: input.potentialProfit,
    model_probability: input.modelProbability,
    book_probability: input.bookProbability,
    edge: input.edge,
    status: "open"
  });

  if (betError) {
    throw new Error(betError.message);
  }

  const { error: accountError } = await supabase
    .from("paper_trading_accounts")
    .update({ balance: nextBalance, updated_at: now })
    .eq("user_id", userId);

  if (accountError) {
    throw new Error(accountError.message);
  }
}

export async function settlePaperBet(
  userId: string,
  currentBalance: number,
  bet: PaperBet,
  status: Exclude<PaperBetStatus, "open">
): Promise<void> {
  const supabase = getSupabaseBrowserClient();

  if (!supabase) {
    throw new Error(missingSupabaseError());
  }

  if (bet.status !== "open") {
    throw new Error("That bet has already been settled.");
  }

  const settledProfit = status === "won" ? bet.potentialProfit : status === "lost" ? -bet.stake : 0;
  const balanceChange = status === "won" ? bet.stake + bet.potentialProfit : status === "void" ? bet.stake : 0;
  const now = new Date().toISOString();

  const { error: betError } = await supabase
    .from("paper_trading_bets")
    .update({
      status,
      settled_profit: settledProfit,
      settled_at: now
    })
    .eq("id", bet.id)
    .eq("user_id", userId);

  if (betError) {
    throw new Error(betError.message);
  }

  const { error: accountError } = await supabase
    .from("paper_trading_accounts")
    .update({ balance: currentBalance + balanceChange, updated_at: now })
    .eq("user_id", userId);

  if (accountError) {
    throw new Error(accountError.message);
  }
}
