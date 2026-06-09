"use client";

import { FormEvent, useState } from "react";
import { useFavorites } from "@/components/FavoritesProvider";
import { sendPasswordReset } from "@/lib/favorites";

export function AuthPanel() {
  const { user, signIn, signUp, signOut } = useFavorites();
  const [mode, setMode] = useState<"login" | "signup" | "forgot">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    setSubmitting(true);

    try {
      const result =
        mode === "forgot"
          ? await sendPasswordReset(email)
          : mode === "login"
            ? await signIn(email, password)
            : await signUp(email, password);

      if (!result.ok) {
        setError(result.error);
        return;
      }

      setMessage(result.message ?? (mode === "login" ? "Logged in." : "Account created."));
      setPassword("");
    } finally {
      setSubmitting(false);
    }
  }

  if (user) {
    return (
      <section className="panel form">
        <p className="eyebrow">Signed in</p>
        <h2>{user.email}</h2>
        <p className="muted">Favorites are saved to your account and sync anywhere you log in.</p>
        <button className="button" onClick={() => void signOut()} type="button">
          Log out
        </button>
      </section>
    );
  }

  return (
    <form className="panel form" onSubmit={handleSubmit}>
      <div className="auth-toggle">
        <button
          className={mode === "login" ? "auth-toggle-btn active" : "auth-toggle-btn"}
          onClick={() => {
            setMode("login");
            setError(null);
            setMessage(null);
          }}
          type="button"
        >
          Log in
        </button>
        <button
          className={mode === "signup" ? "auth-toggle-btn active" : "auth-toggle-btn"}
          onClick={() => {
            setMode("signup");
            setError(null);
            setMessage(null);
          }}
          type="button"
        >
          Sign up
        </button>
      </div>

      <label>
        <p className="muted">Email</p>
        <input
          className="input"
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
          required
          type="email"
          value={email}
        />
      </label>
      {mode !== "forgot" ? (
        <label>
          <p className="muted">Password</p>
          <input
            className="input"
            onChange={(event) => setPassword(event.target.value)}
            placeholder="••••••••"
            required
            type="password"
            value={password}
          />
        </label>
      ) : null}
      <button className="button" disabled={submitting} type="submit">
        {submitting
          ? "Working..."
          : mode === "forgot"
            ? "Send reset email"
            : mode === "login"
              ? "Log in"
              : "Create account"}
      </button>
      {mode === "login" ? (
        <button
          className="auth-link-button"
          onClick={() => {
            setMode("forgot");
            setError(null);
            setMessage(null);
            setPassword("");
          }}
          type="button"
        >
          Forgot password?
        </button>
      ) : null}
      {mode === "forgot" ? (
        <button
          className="auth-link-button"
          onClick={() => {
            setMode("login");
            setError(null);
            setMessage(null);
          }}
          type="button"
        >
          Back to login
        </button>
      ) : null}
      {error ? <p className="form-error">{error}</p> : null}
      {message ? <p className="muted">{message}</p> : null}
      <p className="muted">Real signup and login are powered by Supabase Auth.</p>
    </form>
  );
}
