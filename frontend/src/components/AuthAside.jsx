/**
 * The half of the sign-in and sign-up pages beside the form: what an account
 * is for, and where to read more before making one.
 */
import { Link } from "react-router-dom";

const WHAT_YOU_GET = [
  "Follow writers and see their new articles on your front page",
  "Like and save articles to come back to",
  "Get the monthly digest of the most credible reporting in the topics you choose",
  "Comment on articles and report anything you believe is wrong",
  "Apply to write, with an editor reviewing every article before it is published",
];

export function AuthAside({ lead }) {
  return (
    <aside className="auth-aside">
      <p className="label">Why an account</p>
      <h2 className="heading mt-3">News you can check, on your terms.</h2>
      <p className="lead mt-4">{lead}</p>
      <ul className="auth-benefits mt-6">
        {WHAT_YOU_GET.map((item) => <li key={item}>{item}</li>)}
      </ul>
      <p className="auth-links mt-6">
        <Link className="link-quiet" to="/about-us">About us</Link>
        <Link className="link-quiet" to="/about">How scoring works</Link>
        <Link className="link-quiet" to="/pricing">Pricing</Link>
      </p>
    </aside>
  );
}
