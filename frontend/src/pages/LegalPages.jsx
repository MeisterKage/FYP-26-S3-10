/**
 * Privacy and terms, in plain language.
 *
 * Written from what the code actually does: what is stored, where it goes, and
 * what readers, writers and subscribers agree to. Change these pages whenever
 * that changes (a real payment provider, email delivery, an analytics tool).
 */
import { Link } from "react-router-dom";

import { usePageTitle } from "../usePageTitle";

const UPDATED = "8 October 2026";

function LegalPage({ title, intro, children }) {
  return (
    <div className="legal doc">
      <header className="read">
        <p className="label">Last updated {UPDATED}</p>
        <h1 className="title mt-3">{title}</h1>
        <p className="lead mt-5">{intro}</p>
      </header>
      <div className="read prose mt-7">{children}</div>
    </div>
  );
}

export function PrivacyPage() {
  usePageTitle("Privacy");
  return (
    <LegalPage
      title="Privacy"
      intro="What Wollongong News keeps about you, why, and who else sees it. In short: only what the site needs to work, no advertising trackers, and no selling of anything."
    >
      <h2>What we keep</h2>
      <ul>
        <li>
          <strong>Your account:</strong> your email address, the name you choose to show, and your
          password, stored only as a one-way hash that cannot be turned back into the password.
        </li>
        <li>
          <strong>What you do on the site:</strong> articles you write, comments, likes, saved
          articles, who you follow, sections you choose for your front page, digest subscriptions,
          reports you make, and your notification settings.
        </li>
        <li>
          <strong>Writers:</strong> your articles and their revision history, the sources you cite,
          any cover image you upload, and your accuracy rate, which is public by design.
        </li>
        <li>
          <strong>Subscriptions:</strong> which writers you subscribe to and a record of each
          payment (amount, date, status). We never see or store card details.
        </li>
        <li>
          <strong>Security records:</strong> the internet (IP) address used to sign in, register,
          or take an administrative action, kept in an audit log so misuse can be traced.
        </li>
        <li>
          <strong>View counts</strong> are totals per article. We do not keep a list of which
          articles you have read.
        </li>
      </ul>

      <h2>What stays in your browser</h2>
      <p>
        The site uses no cookies. Your browser keeps your sign-in token, and, if you listen to a
        monthly digest, where you stopped listening. Signing out removes the token; clearing your
        browser&rsquo;s site data removes both.
      </p>

      <h2>Who else is involved</h2>
      <ul>
        <li>
          <strong>Hosting:</strong> the website and its server run on Render, and the database on
          Supabase. They store the data above on our behalf.
        </li>
        <li>
          <strong>Checking sources:</strong> to grade the sources a writer cites, the server looks
          them up with Crossref and Wikidata and may fetch the cited pages. These lookups contain
          the source&rsquo;s address, never anything about you.
        </li>
        <li>
          <strong>Listening:</strong> narration uses the softest female voice your browser offers.
          Some of those voices run online, in which case the text being read (never anything about
          you) goes to your browser&rsquo;s voice service.
        </li>
        <li>
          <strong>Payments:</strong> subscriptions currently run on a test checkout and no money is
          taken. When a real payment provider is connected, your card details will go to that
          provider directly, and this page will name it.
        </li>
      </ul>
      <p>
        There is no advertising, no analytics service, and no third-party tracking. Fonts and
        images are served from this site.
      </p>

      <h2>What is public</h2>
      <p>
        Your display name appears on anything you publish, comment on, or write. A writer&rsquo;s
        accuracy rate, published articles, and any corrections to them are public, because the
        credibility scores depend on them. Your email address is never shown to other users.
      </p>

      <h2>Removing your account</h2>
      <p>
        Ask the site team and an administrator will remove your account. Your email address is
        replaced, your password is cleared, and your comments and likes are deleted. Articles you
        published are either unpublished or kept under &ldquo;Account Removed&rdquo;, because
        readers and other writers&rsquo; scores may rely on them. The audit log keeps its records.
      </p>

      <h2>Changes</h2>
      <p>
        If what the site keeps or who it shares with changes, this page changes first, with a new
        date at the top. See also the <Link className="link" to="/terms">terms of use</Link>.
      </p>
    </LegalPage>
  );
}

export function TermsPage() {
  usePageTitle("Terms of use");
  return (
    <LegalPage
      title="Terms of use"
      intro="The rules for reading, writing and subscribing on Wollongong News. By creating an account you agree to them."
    >
      <h2>Your account</h2>
      <p>
        One account per person. Give a real email address, keep your password to yourself, and tell
        us if you think someone else has used your account. We can suspend an account that breaks
        these terms.
      </p>

      <h2>Credibility scores</h2>
      <p>
        Every score is worked out by fixed, published rules from the writer&rsquo;s track record, the
        sources cited, and any corrections. <Link className="link" to="/about">How scoring works</Link>{" "}
        explains them. A score measures how an article was sourced and how its writer&rsquo;s past
        work has held up. It is not a guarantee that everything in the article is true.
      </p>

      <h2>Writing for the site</h2>
      <ul>
        <li>Submit only your own work, or work you have the right to publish.</li>
        <li>
          Cite your sources. They are graded automatically and checked by an editor, and only the
          five best count towards the score.
        </li>
        <li>
          Every submission is checked for text that matches other articles or its sources. Editors
          may also see automatic writing signals, which prompt a closer look and are never on their
          own a reason to reject your work.
        </li>
        <li>
          Editors may send an article back, publish it, correct it, or retract it. Corrections and
          retractions are public and affect your accuracy rate. You can dispute a correction.
        </li>
        <li>
          AI-generated images are not allowed. You confirm each image you upload is not one, and
          uploads are checked for the marks AI image tools leave in their files.
        </li>
        <li>You keep the rights to your work and let the site publish and display it.</li>
      </ul>

      <h2>Comments and reports</h2>
      <p>
        Keep comments about the article and civil. No harassment, hate, spam, or anyone&rsquo;s
        private information. Moderators may hide comments that break these rules. Use Report for
        articles you believe are wrong or harmful; once enough reports about an article are upheld,
        its score drops, so please report honestly.
      </p>

      <h2>Subscriptions</h2>
      <p>
        Subscribing to a writer costs A$5.00 a month. While a subscription is active you can read
        subscriber-only articles. You can cancel any time from your account; subscriber-only
        articles close again when you cancel. The checkout is currently a test and takes no money.
      </p>

      <h2>Summaries and narration</h2>
      <p>
        &ldquo;In brief&rdquo; summaries and digest summaries are AI generated from the articles
        themselves. Narration is read aloud by a synthetic voice. Read the full article before
        relying on either.
      </p>

      <h2>Changes</h2>
      <p>
        We may update these terms. The date at the top shows when they last changed. See also the{" "}
        <Link className="link" to="/privacy">privacy page</Link>.
      </p>
    </LegalPage>
  );
}
