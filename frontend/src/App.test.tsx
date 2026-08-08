import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppView } from "./App";
import { VttShell } from "./components/VttShell";

describe("AppView", () => {
  it("renders the session loading state", () => {
    render(<AppView auth={{ status: "loading", session: null }} />);

    expect(screen.getByText("Проверяем сессию…")).toBeInTheDocument();
  });

  it("explains missing public configuration", () => {
    render(<AppView auth={{ status: "misconfigured", session: null }} />);

    expect(screen.getByRole("heading", { name: "Supabase ещё не подключён" })).toBeInTheDocument();
  });

  it("renders anonymous landing", () => {
    render(<AppView auth={{ status: "anonymous", session: null }} />);

    expect(screen.getByRole("heading", { name: "Быстрый виртуальный стол" })).toBeInTheDocument();
  });

  it("renders the authenticated workspace shell", () => {
    render(<VttShell userLabel="Гейм-мастер" />);

    expect(screen.getByRole("main")).toHaveClass("app-shell");
    expect(screen.getByRole("region", { name: "Игровая сцена" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Библиотека материалов" })).toBeInTheDocument();
  });
});
