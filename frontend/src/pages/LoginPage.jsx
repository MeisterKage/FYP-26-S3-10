/**
 * Sign in (PDD Figure 5.9).
 *
 * Two columns on wide screens: the form, and a standing note about what the
 * platform is. A bare centred form on an otherwise empty page wastes the one
 * moment a returning reader is looking straight at the masthead.
 */
import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../api";
import { useAuth } from "../auth";
import { Button, Field, Notice } from "../components/UI";

export default function LoginPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState(null);
  const [fieldError, setFieldError] = useState(null);
  const [busy, setBusy] = useState(false);

  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value });

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setFieldError(null);

    try {
      await signIn(form.email, form.password);
      navigate(location.state?.from || "/", { replace: true });
    } catch (e) {
      if (e instanceof ApiError && e.field) setFieldError({ [e.field]: e.message });
      else setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <div className="auth-form">
        <h1 className="title">Sign in</h1>

        <form className="form mt-6" onSubmit={submit} noValidate>
          {error && <Notice>{error}</Notice>}

          <Field label="Email" id="email" error={fieldError?.email}>
            {(props) => (
              <input
                {...props}
                className="input"
                type="email"
                autoComplete="email"
                value={form.email}
                onChange={set("email")}
                required
              />
            )}
          </Field>

          <Field label="Password" id="password" error={fieldError?.password}>
            {(props) => (
              <input
                {...props}
                className="input"
                type="password"
                autoComplete="current-password"
                value={form.password}
                onChange={set("password")}
                required
              />
            )}
          </Field>

          <div className="row gap-5">
            <Button variant="primary" type="submit" busy={busy}>
              {busy ? "Signing in" : "Sign in"}
            </Button>
            <Link className="link-quiet" to="/register">
              Create an account
            </Link>
            <Link className="link-quiet" to="/reset-password">
              Forgot your password?
            </Link>
          </div>
        </form>
      </div>

      <aside className="auth-aside">
        <p className="lead">
          Every article on The Record carries a credibility score produced by a
          fixed set of rules. The working sits beside the article, where you can
          check it.
        </p>
        <Link className="link-quiet mt-5" to="/about" style={{ display: "inline-block" }}>
          How scoring works
        </Link>
      </aside>
    </div>
  );
}
