/**
 * Password reset (PDD Figure 5.11).
 *
 * One page, two states, chosen by whether a token is in the URL. The request
 * form deliberately gives the same answer whether or not the address is
 * registered: a form that says "no such account" is a way to enumerate users,
 * and the server already refuses to distinguish the two.
 *
 * v1 logs the reset email rather than sending it (integrations.py), so the
 * page says how to obtain the link instead of pretending one is in flight.
 */
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../api";
import { Button, Field, Notice } from "../components/UI";

const MIN_PASSWORD = 12;

function RequestForm() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/password-reset/request", { email });
      setSent(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <Notice tone="quiet">
        If that address is registered, a reset link is on its way. The same answer
        is given either way, so this page cannot be used to discover which
        accounts exist.
      </Notice>
    );
  }

  return (
    <form className="form" onSubmit={submit}>
      {error && <Notice>{error}</Notice>}
      <Field label="Email" id="email">
        {(props) => (
          <input
            {...props}
            className="input"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        )}
      </Field>
      <div className="row gap-4 mt-6">
        <Button variant="primary" type="submit" busy={busy} disabled={!email.trim()}>
          Send a reset link
        </Button>
        <Link className="link-quiet" to="/login">
          Back to sign in
        </Link>
      </div>
    </form>
  );
}

function ConfirmForm({ token }) {
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [fieldError, setFieldError] = useState(null);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setFieldError(null);
    try {
      await api.post("/auth/password-reset/confirm", { token, password });
      setDone(true);
    } catch (e) {
      if (e.field === "password") setFieldError(e.message);
      else setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <>
        <Notice tone="quiet">
          Password changed. Any session opened with the old one is no longer valid.
        </Notice>
        <div className="mt-6">
          <Link className="btn btn-primary" to="/login">
            Sign in
          </Link>
        </div>
      </>
    );
  }

  const short = password.length > 0 && password.length < MIN_PASSWORD;

  return (
    <form className="form" onSubmit={submit}>
      {error && <Notice>{error}</Notice>}
      <Field
        label="New password"
        id="password"
        hint={`At least ${MIN_PASSWORD} characters.`}
        error={
          fieldError ||
          (short ? `${MIN_PASSWORD - password.length} more characters needed.` : null)
        }
      >
        {(props) => (
          <input
            {...props}
            className="input"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        )}
      </Field>
      <div className="row gap-4 mt-6">
        <Button
          variant="primary"
          type="submit"
          busy={busy}
          disabled={password.length < MIN_PASSWORD}
        >
          Set new password
        </Button>
      </div>
    </form>
  );
}

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token");

  return (
    <div className="auth">
      <div className="auth-form">
        <h1 className="title">{token ? "Choose a new password" : "Reset your password"}</h1>
        <p className="lead mt-4">
          {token
            ? "This link works once, and only for a limited time."
            : "We will email a link that lets you set a new password."}
        </p>

        <div className="mt-6">{token ? <ConfirmForm token={token} /> : <RequestForm />}</div>
      </div>

      <aside className="auth-aside">
        <p className="lead">
          Email is not yet connected in this version, so the reset link is written
          to the server log rather than delivered. An administrator can read it
          there.
        </p>
      </aside>
    </div>
  );
}
