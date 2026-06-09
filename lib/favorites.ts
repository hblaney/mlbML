export type LocalUser = {
  email: string;
  createdAt: string;
};

export type FavoritePlayer = {
  id: number;
  name: string;
  team: string;
  position: string;
  headshotUrl: string;
  number?: string | null;
  bats?: string | null;
  throws?: string | null;
  hitting?: Record<string, string | number> | null;
  pitching?: Record<string, string | number> | null;
};

export type FavoritesState = {
  teamIds: string[];
  players: FavoritePlayer[];
};

const USERS_KEY = "mlb-edge-users";
const SESSION_KEY = "mlb-edge-session";
const FAVORITES_PREFIX = "mlb-edge-favorites:";

type StoredUser = {
  email: string;
  password: string;
  createdAt: string;
};

function isBrowser() {
  return typeof window !== "undefined";
}

function readUsers(): StoredUser[] {
  if (!isBrowser()) {
    return [];
  }

  try {
    const raw = localStorage.getItem(USERS_KEY);
    return raw ? (JSON.parse(raw) as StoredUser[]) : [];
  } catch {
    return [];
  }
}

function writeUsers(users: StoredUser[]) {
  if (!isBrowser()) {
    return;
  }

  localStorage.setItem(USERS_KEY, JSON.stringify(users));
}

function favoritesKey(email: string) {
  return `${FAVORITES_PREFIX}${email.toLowerCase()}`;
}

export function getSession(): LocalUser | null {
  if (!isBrowser()) {
    return null;
  }

  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as LocalUser) : null;
  } catch {
    return null;
  }
}

export function setSession(user: LocalUser | null) {
  if (!isBrowser()) {
    return;
  }

  if (!user) {
    localStorage.removeItem(SESSION_KEY);
    return;
  }

  localStorage.setItem(SESSION_KEY, JSON.stringify(user));
}

export function signUp(email: string, password: string): { ok: true } | { ok: false; error: string } {
  const normalizedEmail = email.trim().toLowerCase();

  if (!normalizedEmail || !password) {
    return { ok: false, error: "Email and password are required." };
  }

  if (password.length < 6) {
    return { ok: false, error: "Password must be at least 6 characters." };
  }

  const users = readUsers();

  if (users.some((user) => user.email === normalizedEmail)) {
    return { ok: false, error: "An account with that email already exists." };
  }

  const createdAt = new Date().toISOString();
  users.push({ email: normalizedEmail, password, createdAt });
  writeUsers(users);
  setSession({ email: normalizedEmail, createdAt });

  return { ok: true };
}

export function signIn(email: string, password: string): { ok: true } | { ok: false; error: string } {
  const normalizedEmail = email.trim().toLowerCase();
  const user = readUsers().find((item) => item.email === normalizedEmail);

  if (!user || user.password !== password) {
    return { ok: false, error: "Invalid email or password." };
  }

  setSession({ email: user.email, createdAt: user.createdAt });
  return { ok: true };
}

export function signOut() {
  setSession(null);
}

export function loadFavorites(email: string): FavoritesState {
  if (!isBrowser()) {
    return { teamIds: [], players: [] };
  }

  try {
    const raw = localStorage.getItem(favoritesKey(email));
    if (!raw) {
      return { teamIds: [], players: [] };
    }

    const parsed = JSON.parse(raw) as FavoritesState;
    return {
      teamIds: Array.isArray(parsed.teamIds) ? parsed.teamIds : [],
      players: Array.isArray(parsed.players) ? parsed.players : []
    };
  } catch {
    return { teamIds: [], players: [] };
  }
}

export function saveFavorites(email: string, favorites: FavoritesState) {
  if (!isBrowser()) {
    return;
  }

  localStorage.setItem(favoritesKey(email), JSON.stringify(favorites));
}
