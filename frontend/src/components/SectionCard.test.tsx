import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SectionCard from "./SectionCard";
import type { SectionResult } from "../types";

const SECTION: SectionResult = {
  file: "README.md", section_id: "README.md#users", symbol_id: "create_user",
  route: "autofix",
  confidence: 0.9, reason: "signature changed", wrong_claims: ["create_user"],
  diff: "-Use `create_user(name)`\n+Use `create_user(name, email)`",
};

describe("SectionCard", () => {
  it("shows the section id, route badge, and diff", () => {
    render(<SectionCard section={SECTION} />);
    expect(screen.getByText("README.md#users")).toBeInTheDocument();
    expect(screen.getByText(/autofix/i)).toBeInTheDocument();
    expect(screen.getByText(/create_user\(name, email\)/)).toBeInTheDocument();
  });
});
