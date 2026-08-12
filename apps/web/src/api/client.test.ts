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

  it("does not expose legacy command or agent write helpers", () => {
    const legacy = ["run" + "Command", "invoke" + "Agent"] as const;
    for (const name of legacy) {
      expect(Object.prototype.hasOwnProperty.call(api, name)).toBe(false);
    }
  });
});

describe("postMessage", () => {
  it("posts role, body and model_key to the messages endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ messages: [], summary: null }),
    });
    vi.stubGlobal("fetch", fetchMock);
    await api.postMessage("dummy-01", "seller", "@agent confirm", "sonnet-4-6");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/customers/dummy-01/messages");
    expect(JSON.parse(init.body)).toEqual({
      role: "seller", body: "@agent confirm", model_key: "sonnet-4-6",
    });
    vi.unstubAllGlobals();
  });
});

describe("buildProduct", () => {
  it("posts to the product build endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: "PX-100", code: "PX-100", name: "P", short_description: "d", long_description: null, spec: null, metadata: {}, build_status: "built" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const result = await api.buildProduct("PX-100");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/products/PX-100/build");
    expect(init.method).toBe("POST");
    expect(result.build_status).toBe("built");
    vi.unstubAllGlobals();
  });
});

it("passes org_id as a query param when listing products", async () => {
  const fetchMock = vi.fn(async () => new Response("[]", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  await api.listProducts("pym");
  expect(fetchMock.mock.calls[0][0]).toBe("/api/products?org_id=pym");
  await api.listProducts();
  expect(fetchMock.mock.calls[1][0]).toBe("/api/products");
  vi.unstubAllGlobals();
});
