create table if not exists public.user_favorites (
  user_id uuid primary key references auth.users(id) on delete cascade,
  team_ids text[] not null default '{}',
  players jsonb not null default '[]',
  updated_at timestamptz not null default now()
);

alter table public.user_favorites enable row level security;

drop policy if exists "Users can read their own favorites" on public.user_favorites;
create policy "Users can read their own favorites"
on public.user_favorites
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists "Users can insert their own favorites" on public.user_favorites;
create policy "Users can insert their own favorites"
on public.user_favorites
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists "Users can update their own favorites" on public.user_favorites;
create policy "Users can update their own favorites"
on public.user_favorites
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

create table if not exists public.paper_trading_accounts (
  user_id uuid primary key references auth.users(id) on delete cascade,
  starting_balance numeric(12, 2) not null default 10000.00,
  balance numeric(12, 2) not null default 10000.00,
  updated_at timestamptz not null default now()
);

create table if not exists public.paper_trading_bets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  game_id text not null,
  starts_at timestamptz not null,
  matchup text not null,
  team_id text not null,
  team_name text not null,
  opponent_id text not null,
  opponent_name text not null,
  side text not null default 'Moneyline',
  odds integer not null,
  stake numeric(12, 2) not null,
  potential_profit numeric(12, 2) not null,
  model_probability numeric(8, 4),
  book_probability numeric(8, 4),
  edge numeric(8, 4),
  status text not null default 'open' check (status in ('open', 'won', 'lost', 'void')),
  settled_profit numeric(12, 2),
  placed_at timestamptz not null default now(),
  settled_at timestamptz
);

alter table public.paper_trading_accounts enable row level security;
alter table public.paper_trading_bets enable row level security;

drop policy if exists "Users can read their own paper account" on public.paper_trading_accounts;
create policy "Users can read their own paper account"
on public.paper_trading_accounts
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists "Users can insert their own paper account" on public.paper_trading_accounts;
create policy "Users can insert their own paper account"
on public.paper_trading_accounts
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists "Users can update their own paper account" on public.paper_trading_accounts;
create policy "Users can update their own paper account"
on public.paper_trading_accounts
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "Users can read their own paper bets" on public.paper_trading_bets;
create policy "Users can read their own paper bets"
on public.paper_trading_bets
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists "Users can insert their own paper bets" on public.paper_trading_bets;
create policy "Users can insert their own paper bets"
on public.paper_trading_bets
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists "Users can update their own paper bets" on public.paper_trading_bets;
create policy "Users can update their own paper bets"
on public.paper_trading_bets
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "Users can delete their own paper bets" on public.paper_trading_bets;
create policy "Users can delete their own paper bets"
on public.paper_trading_bets
for delete
to authenticated
using (auth.uid() = user_id);
