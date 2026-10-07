import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import App from "@/App"
import { mockFetch, renderWithQuery } from "@/test/utils"

function renderAt(route: string) {
  mockFetch(() => ({ body: [] }))
  renderWithQuery(<App />, route)
}

const calendarShown = () => screen.findByRole("group", { name: "Calendar view" }, { timeout: 2000 })

describe("Sign in", () => {
  it("is the main page", () => {
    renderAt("/")
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Continue with Google" })).toBeInTheDocument()
  })

  it("renders on /login", () => {
    renderAt("/login")
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Continue with Google" })).toBeInTheDocument()
  })

  it("validates email and password", async () => {
    renderAt("/")
    await userEvent.type(screen.getByLabelText("Email"), "not-an-email")
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }))
    expect(await screen.findByText("Enter a valid email")).toBeInTheDocument()
    expect(screen.getByText("Password is required")).toBeInTheDocument()
  })

  it("opens the calendar after signing in", async () => {
    renderAt("/")
    await userEvent.type(screen.getByLabelText("Email"), "anna@example.com")
    await userEvent.type(screen.getByLabelText("Password"), "secret")
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }))
    expect(await calendarShown()).toBeInTheDocument()
  })

  it("shows Google as coming soon until it is enabled", () => {
    renderAt("/")
    expect(screen.getByRole("button", { name: "Continue with Google" })).toBeDisabled()
    expect(screen.getByText("Google sign-in is coming soon.")).toBeInTheDocument()
  })

  it("links to sign up", async () => {
    renderAt("/")
    await userEvent.click(screen.getByRole("link", { name: "Sign up" }))
    expect(screen.getByRole("heading", { name: "Create an account" })).toBeInTheDocument()
  })
})

describe("Sign up", () => {
  it("checks password length and confirmation", async () => {
    renderAt("/signup")
    await userEvent.type(screen.getByLabelText("Name"), "Anna")
    await userEvent.type(screen.getByLabelText("Email"), "anna@example.com")
    await userEvent.type(screen.getByLabelText("Password"), "short")
    await userEvent.type(screen.getByLabelText("Confirm password"), "different")
    await userEvent.click(screen.getByRole("button", { name: "Create account" }))
    expect(await screen.findByText("At least 8 characters")).toBeInTheDocument()
    expect(screen.getByText("Passwords do not match")).toBeInTheDocument()
  })

  it("opens the calendar after creating an account", async () => {
    renderAt("/signup")
    await userEvent.type(screen.getByLabelText("Name"), "Anna")
    await userEvent.type(screen.getByLabelText("Email"), "anna@example.com")
    await userEvent.type(screen.getByLabelText("Password"), "long-enough1")
    await userEvent.type(screen.getByLabelText("Confirm password"), "long-enough1")
    await userEvent.click(screen.getByRole("button", { name: "Create account" }))
    expect(await calendarShown()).toBeInTheDocument()
  })

  it("shows/hides the password", async () => {
    renderAt("/signup")
    const password = screen.getByLabelText("Password")
    expect(password).toHaveAttribute("type", "password")
    await userEvent.click(screen.getAllByRole("button", { name: "Show password" })[0])
    expect(password).toHaveAttribute("type", "text")
  })
})
