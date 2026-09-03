/**
 * Create an account (PDD Figure 5.1).
 *
 * Registration also captures category interests, because the personalised feed
 * has nothing to work with otherwise and a new reader would land on a page that
 * looks broken.
 */
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { Button, Field, Notice } from "../components/UI";

const MIN_PASSWORD = 12;

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [categories, setCategories] = useState([]);
  const [form, setForm] = useState({ displayName: "", email: "", password: "" });
  const [selected, setSelected] = useState([]);
  const [error, setError] = useState(null);
  const [fieldError, setFieldError] = useState({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get("/categories")
      .then((data) => setCategories(data.categories))
      .catch(() => {
        /* Interests are optional; a failure here must not block signing up. */
      });
  }, []);

  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value });

  function toggle(id) {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setFieldError({});

    try {
      await register({ ...form, categoryIds: selected });
      navigate("/", { replace: true });
    } catch (e) {
      if (e instanceof ApiError && e.field) setFieldError({ [e.field]: e.message });
      else setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const short = form.password.length > 0 && form.password.length < MIN_PASSWORD;

  return (
    <div className="auth">
      <div className="auth-form">
        <h1 className="title">Create an account</h1>
        <p className="lead mt-4">
          Comment, follow writers, save what you are reading, and apply to write.
        </p>

        <form className="form mt-6" onSubmit={submit} noValidate>
          {error && <Notice>{error}</Notice>}

          <Field label="Your name" id="name" error={fieldError.displayName}>
            {(props) => (
              <input
                {...props}
                className="input"
                autoComplete="name"
                value={form.displayName}
                onChange={set("displayName")}
                required
              />
            )}
          </Field>

          <Field label="Email" id="email" error={fieldError.email}>
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

          <Field
            label="Password"
            id="password"
            hint={`At least ${MIN_PASSWORD} characters.`}
            error={
              fieldError.password ||
              (short ? `${MIN_PASSWORD - form.password.length} more characters needed.` : null)
            }
          >
            {(props) => (
              <input
                {...props}
                className="input"
                type="password"
                autoComplete="new-password"
                value={form.password}
                onChange={set("password")}
                required
              />
            )}
          </Field>

          {categories.length > 0 && (
            <fieldset className="fieldset">
              <legend className="field-label">
                What are you interested in?
                <span className="field-hint"> Optional. Shapes your front page.</span>
              </legend>
              <div className="chips mt-3">
                {categories.map((category) => (
                  <button
                    type="button"
                    key={category.id}
                    className="chip"
                    aria-pressed={selected.includes(category.id)}
                    onClick={() => toggle(category.id)}
                  >
                    {category.name}
                  </button>
                ))}
              </div>
            </fieldset>
          )}

          <div className="row gap-5">
            <Button variant="primary" type="submit" busy={busy} disabled={short}>
              {busy ? "Creating account" : "Create account"}
            </Button>
            <Link className="link-quiet" to="/login">
              Already have an account?
            </Link>
          </div>
        </form>
      </div>

      <aside className="auth-aside">
        <p className="lead">
          Writing here is by application. Anyone can read, comment, and report an
          inaccuracy; publishing requires an editor&rsquo;s approval, and every
          article you publish carries your accuracy rate with it.
        </p>
        <Link className="link-quiet mt-5" to="/about" style={{ display: "inline-block" }}>
          How scoring works
        </Link>
      </aside>
    </div>
  );
}
