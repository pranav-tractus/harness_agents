import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgreementGlyph, BuildBadge, agreementLevel } from "./parts";

describe("agreementLevel", () => {
  it("maps both parties to 'both'", () => {
    expect(agreementLevel(["seller", "customer"])).toBe("both");
  });
  it("maps a single party to 'one'", () => {
    expect(agreementLevel(["seller"])).toBe("one");
  });
  it("maps empty / non-array to 'none'", () => {
    expect(agreementLevel([])).toBe("none");
    expect(agreementLevel(undefined)).toBe("none");
  });
});

describe("AgreementGlyph", () => {
  it("renders the both-parties glyph", () => {
    render(<AgreementGlyph agreedBy={["seller", "customer"]} />);
    expect(screen.getByText("✅")).toBeInTheDocument();
  });
});

describe("BuildBadge", () => {
  it("renders the build status text", () => {
    render(<BuildBadge status="stale" />);
    expect(screen.getByText("stale")).toBeInTheDocument();
  });
});
