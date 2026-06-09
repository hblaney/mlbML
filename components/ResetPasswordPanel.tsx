"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { updatePassword } from "@/lib/favorites";

export function ResetPasswordPanel() {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setSubmitting(true);

    try {
      const result = await updatePassword(password);

      if (!result.ok) {
        setError(result.error);
        return;
      }

      setMessage(result.message ?? "Password updated.");
      setPassword("");
      setConfirmPassword("");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="panel form" onSubmit={handleSubmit}>
      <p className="eyebrow">Account recovery</p>
      <h2>Set a new password</h2>
      <p className="muted">Enter a new password after opening the reset link from your email.</p>

      <label>
        <p className="muted">New password</p>
        <input
          className="input"
          onChange={(event) => setPassword(event.target.value)}
          placeholder="••••••••"
          required
          type="password"
          value={password}
        />
      </label>
      <label>
        <p className="muted">Confirm password</p>
        <input
          className="input"
          onChange={(event) => setConfirmPassword(event.target.value)}
          placeholder="••••••••"
          required
          type="password"
          value={confirmPassword}
        />
      </label>
      <button className="button" disabled={submitting} type="submit">
        {submitting ? "Updating..." : "Update password"}
      </button>
      {error ? <p className="form-error">{error}</p> : null}
      {message ? (
        <>
          <p className="muted">{message}</p>
          <Link className="button secondary" href="/login">
            Back to login
          </Link>
        </>
      ) : null}
    </form>
  );
}
