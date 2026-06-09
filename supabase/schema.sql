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
