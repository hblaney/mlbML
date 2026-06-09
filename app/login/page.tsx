import { AuthPanel } from "@/components/AuthPanel";

export default function LoginPage() {
  return (
    <main className="shell">
      <section className="hero">
        <div>
          <p className="eyebrow">User accounts</p>
          <h1>Log in and track your teams.</h1>
          <p className="lead">
            Create an account to save favorite teams and players. Your board syncs anywhere you log in.
          </p>
        </div>

        <AuthPanel />
      </section>
    </main>
  );
}
