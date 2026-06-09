export default function LoginPage() {
  return (
    <main className="shell">
      <section className="hero">
        <div>
          <p className="eyebrow">User accounts</p>
          <h1>Log in and track your teams.</h1>
          <p className="lead">
            This page is ready to connect to Supabase Auth. Once keys are added, users can save favorite teams,
            personalize the dashboard, and track prediction history.
          </p>
        </div>

        <form className="panel form">
          <label>
            <p className="muted">Email</p>
            <input className="input" type="email" placeholder="you@example.com" />
          </label>
          <label>
            <p className="muted">Password</p>
            <input className="input" type="password" placeholder="••••••••" />
          </label>
          <button className="button" type="button">Continue</button>
          <p className="muted">
            Supabase connection is intentionally left as environment setup so secrets never get committed.
          </p>
        </form>
      </section>
    </main>
  );
}
