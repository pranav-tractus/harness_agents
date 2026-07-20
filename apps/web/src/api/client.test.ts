import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./client";

beforeEach(() => {
  global.fetch = vi.fn(async () =>
    ({
      ok: true,
      json: async () => [{ id: "dummy-01", name: "Dummy-01" }],
    }) as Response,
  );
});

describe("api client", () => {
  it("lists customers via /api/customers", async () => {
    const rows = await api.listCustomers();
    expect(global.fetch).toHaveBeenCalledWith("/api/customers", expect.anything());
    expect(rows[0].id).toBe("dummy-01");
  });

  it("runCommand posts to the commands endpoint", async () => {
    await api.runCommand("dummy-01", "approve", null, "sonnet-4-6");
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/customers/dummy-01/commands",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("invokeAgent", () => {
  it("posts action and model_key", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ messages: [], summary: null }),
    });
    vi.stubGlobal("fetch", fetchMock);
    await api.invokeAgent("dummy-01", "sonnet-4-6", "ask");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/customers/dummy-01/agent");
    expect(JSON.parse(init.body)).toEqual({ model_key: "sonnet-4-6", action: "ask" });
    vi.unstubAllGlobals();
  });
});
