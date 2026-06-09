import { ResetPasswordPanel } from "@/components/ResetPasswordPanel";

export default function ResetPasswordPage() {
  return (
    <main className="shell">
      <section className="hero">
        <div>
          <p className="eyebrow">Password reset</p>
          <h1>Recover your MLB Edge account.</h1>
          <p className="lead">
            Open this page from the reset link in your email, then choose a new password for your account.
          </p>
        </div>

        <ResetPasswordPanel />
      </section>
    </main>
  );
}
