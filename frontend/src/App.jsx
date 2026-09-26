/**
 * Route table and page shell.
 *
 * Role checks here govern navigation only. Flask decides what a request may do
 * (PDD Section 3); hiding a link is a courtesy, not a control.
 */
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { CAN_ADMIN, CAN_AUTHOR, CAN_REVIEW, ROLES, useAuth } from "./auth";
import { ErrorBoundary, Footer, Masthead } from "./components/Layout";
import { Button, Empty } from "./components/UI";
import AboutPage from "./pages/AboutPage";
import Account from "./pages/Account";
import AdminConsole from "./pages/AdminConsole";
import ArticleEditor from "./pages/ArticleEditor";
import ArticlePage from "./pages/ArticlePage";
import ContributorDashboard from "./pages/ContributorDashboard";
import CategoryPage from "./pages/CategoryPage";
import ContributorProfile from "./pages/ContributorProfile";
import { CountryIndex, CountryPage } from "./pages/CountryPages";
import { DigestArchive, DigestEdition } from "./pages/Digests";
import { EditorPanel, EditorProfile } from "./pages/EditorPanel";
import ResetPassword from "./pages/ResetPassword";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import PricingPage from "./pages/PricingPage";
import Moderation from "./pages/Moderation";
import RegisterPage from "./pages/RegisterPage";
import ReviewQueue from "./pages/ReviewQueue";
import SearchPage from "./pages/SearchPage";

function RequireRole({ roles, children }) {
  const { user, loading, has } = useAuth();
  const location = useLocation();

  // Still resolving /auth/me. Redirecting first would bounce a signed-in user
  // to the login page on every hard refresh.
  if (loading) {
    return <div className="skeleton" style={{ height: "16rem" }} aria-hidden="true" />;
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  if (roles && !has(...roles)) {
    return (
      <Empty title="You don't have access to this page">
        This area is for {roles.includes(ROLES.EDITOR) ? "editors" : "writers"}. If
        that should include you, an administrator can change your role.
      </Empty>
    );
  }

  return children;
}

function NotFound() {
  return (
    <Empty
      title="That page isn't here"
      action={
        <Button variant="outline" as="a" href="/" className="mt-4">
          Back to the front page
        </Button>
      }
    >
      The link may be old, or the article may have been unpublished.
    </Empty>
  );
}

export default function App() {
  return (
    <>
      <a className="skip" href="#main">
        Skip to content
      </a>

      <Masthead />

      <main className="shell main" id="main" tabIndex={-1}>
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="/pricing" element={<PricingPage />} />
            <Route path="/articles/:slug" element={<ArticlePage />} />
            <Route path="/categories/:slug" element={<CategoryPage />} />
            <Route path="/contributors/:id" element={<ContributorProfile />} />
            <Route path="/countries" element={<CountryIndex />} />
            <Route path="/countries/:code" element={<CountryPage />} />
            <Route path="/digests" element={<DigestArchive />} />
            <Route path="/digests/:month/:key" element={<DigestEdition />} />
            <Route path="/editors" element={<EditorPanel />} />
            <Route path="/editors/:id" element={<EditorProfile />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route
              path="/dashboard"
              element={
                <RequireRole roles={CAN_AUTHOR}>
                  <ContributorDashboard />
                </RequireRole>
              }
            />
            <Route
              path="/dashboard/articles/:id"
              element={
                <RequireRole roles={CAN_AUTHOR}>
                  <ArticleEditor />
                </RequireRole>
              }
            />
            <Route
              path="/review"
              element={
                <RequireRole roles={CAN_REVIEW}>
                  <ReviewQueue />
                </RequireRole>
              }
            />
            <Route
              path="/account"
              element={
                <RequireRole roles={Object.values(ROLES)}>
                  <Account />
                </RequireRole>
              }
            />
            <Route
              path="/moderation"
              element={
                <RequireRole roles={CAN_REVIEW}>
                  <Moderation />
                </RequireRole>
              }
            />
            <Route
              path="/admin"
              element={
                <RequireRole roles={CAN_ADMIN}>
                  <AdminConsole />
                </RequireRole>
              }
            />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </ErrorBoundary>
      </main>

      <Footer />
    </>
  );
}
