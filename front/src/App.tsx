import { Navigate, Route, Routes } from "react-router"

import { RedirectIfSignedIn, RequireAuth } from "@/components/auth/RequireAuth"
import { AuthCallbackPage } from "@/pages/AuthCallbackPage"
import { ConfirmPage } from "@/pages/ConfirmPage"
import { HomePage } from "@/pages/HomePage"
import { LoginPage } from "@/pages/LoginPage"
import { SignUpPage } from "@/pages/SignUpPage"

export default function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <RedirectIfSignedIn>
            <LoginPage />
          </RedirectIfSignedIn>
        }
      />
      <Route
        path="/login"
        element={
          <RedirectIfSignedIn>
            <LoginPage />
          </RedirectIfSignedIn>
        }
      />
      <Route
        path="/signup"
        element={
          <RedirectIfSignedIn>
            <SignUpPage />
          </RedirectIfSignedIn>
        }
      />
      <Route path="/confirm" element={<ConfirmPage />} />
      <Route path="/auth/callback" element={<AuthCallbackPage />} />
      <Route
        path="/home"
        element={
          <RequireAuth>
            <HomePage />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
