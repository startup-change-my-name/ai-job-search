import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { OperationsCockpit } from "./OperationsCockpit";

describe("OperationsCockpit", () => {
  it("renders foundation service health and future workflow zero states", () => {
    render(
      <OperationsCockpit
        status={{
          generated_at: "2026-09-21T12:00:00Z",
          services: [
            {
              name: "postgres",
              state: "healthy",
              checked_at: "2026-09-21T12:00:00Z",
            },
            {
              name: "airflow",
              state: "degraded",
              checked_at: "2026-09-21T12:00:00Z",
            },
          ],
        }}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Operations cockpit" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Postgres")).toBeInTheDocument();
    expect(screen.getByText("Airflow")).toBeInTheDocument();
    expect(screen.getByText("Approval ready")).toBeInTheDocument();
    expect(screen.getByText("Manual actions")).toBeInTheDocument();
    expect(screen.getByText("Follow-ups due")).toBeInTheDocument();
  });
});
