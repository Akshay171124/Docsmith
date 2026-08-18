import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import AnalyzeForm from "./AnalyzeForm";

describe("AnalyzeForm", () => {
  it("switches the credential label with the backend", async () => {
    render(<AnalyzeForm onSubmit={vi.fn()} pending={false} />);
    expect(screen.getByLabelText(/ollama host/i)).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/claude/i));
    expect(screen.getByLabelText(/anthropic api key/i)).toBeInTheDocument();
  });
});
