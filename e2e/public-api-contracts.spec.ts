import { expect, test, type APIRequestContext } from "@playwright/test";

type PublicGetContract = {
  path: string;
  contentType: RegExp;
  json?: true;
};

const publicGetContracts: PublicGetContract[] = [
  { path: "/", contentType: /text\/html/ },
  { path: "/weekly-review", contentType: /text\/html/ },
  { path: "/assets/weekly-review.js", contentType: /(?:text|application)\/javascript/ },
  { path: "/daily-market-brief", contentType: /text\/html/ },
  { path: "/assets/daily-market-brief.js", contentType: /(?:text|application)\/javascript/ },
  { path: "/health", contentType: /application\/json/, json: true },
  { path: "/command", contentType: /text\/html/ },
  { path: "/api/command-workbench/actions", contentType: /application\/json/, json: true },
  { path: "/api/weekly-review", contentType: /application\/json/, json: true },
  { path: "/api/daily-market-brief", contentType: /application\/json/, json: true },
  { path: "/api/daily-market-brief/dates", contentType: /application\/json/, json: true },
  { path: "/api/daily-market-brief/history-jobs", contentType: /application\/json/, json: true },
  { path: "/ai-industry-panorama", contentType: /text\/html/ },
  { path: "/assets/ai-industry-panorama.js", contentType: /(?:text|application)\/javascript/ },
  { path: "/api/ai-industry-panorama", contentType: /application\/json/, json: true },
];

for (const contract of publicGetContracts) {
  test(`public GET contract: ${contract.path}`, async ({ request }) => {
    const response = await request.get(contract.path);

    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).toMatch(contract.contentType);
    expect((await response.body()).length).toBeGreaterThan(0);
    if (contract.json) {
      expect((await response.json()).ok).toBe(true);
    }
  });
}

const protectedContracts = [
  { method: "get", path: "/api/candidate-insights" },
  { method: "post", path: "/api/command-workbench/parse" },
  { method: "post", path: "/api/command-workbench/execute" },
  { method: "post", path: "/command" },
  { method: "post", path: "/api/weekly-review/generate" },
  { method: "post", path: "/api/weekly-review/refresh" },
  { method: "post", path: "/api/weekly-review/save" },
  { method: "post", path: "/api/candidate-insights/1/confirm" },
  { method: "post", path: "/api/candidate-insights/1/reject" },
] as const;

const admittedDailyMarkets = ["CN", "HK", "US"] as const;

async function readDailyMutationState(request: APIRequestContext) {
  const [historyJobsResponse, ...savedDatesResponses] = await Promise.all([
    request.get("/api/daily-market-brief/history-jobs"),
    ...admittedDailyMarkets.map((market) =>
      request.get(`/api/daily-market-brief/dates?market=${market}`),
    ),
  ]);

  expect(historyJobsResponse.status()).toBe(200);
  for (const savedDatesResponse of savedDatesResponses) {
    expect(savedDatesResponse.status()).toBe(200);
  }

  const [historyJobs, ...savedDates] = await Promise.all([
    historyJobsResponse.json(),
    ...savedDatesResponses.map((response) => response.json()),
  ]);

  return {
    historyJobIds: historyJobs.jobs.map((job: { id: number }) => job.id),
    savedDatesByMarket: Object.fromEntries(
      admittedDailyMarkets.map((market, index) => [market, savedDates[index].dates]),
    ),
  };
}

for (const contract of protectedContracts) {
  test(`tokenless protected boundary: ${contract.method.toUpperCase()} ${contract.path}`, async ({ request }) => {
    const response = await request[contract.method](contract.path, {
      maxRedirects: 0,
    });

    expect(response.status()).toBe(401);
    expect(response.headers()["content-type"]).toMatch(/application\/json/);
    const payload = await response.json();
    expect(payload).toMatchObject({
      error: "access_required",
      recovery: { next_action: "enter_access", retryable: true },
    });
  });
}

test("Daily generate rejects unsupported fields before generation", async ({ request }) => {
  const stateBefore = await readDailyMutationState(request);
  const response = await request.post("/api/daily-market-brief/generate", {
    data: { force: true },
  });
  const payload = await response.json();

  expect(response.status()).toBe(400);
  expect(payload).toMatchObject({
    ok: false,
    error: "公开生成不支持 force、batch 或其他工作量控制参数。",
  });
  expect(await readDailyMutationState(request)).toEqual(stateBefore);
});

test("Daily history job creation rejects an invalid shape before mutation", async ({ request }) => {
  const stateBefore = await readDailyMutationState(request);
  const response = await request.post("/api/daily-market-brief/history-jobs", {
    data: {},
  });
  const payload = await response.json();

  expect(response.status()).toBe(400);
  expect(payload).toMatchObject({
    ok: false,
    error: "历史简报任务只接受 market 和 date。",
  });
  expect(await readDailyMutationState(request)).toEqual(stateBefore);
});

test("AI Industry Panorama public API exposes a reviewed, safe, two-hop release", async ({ request }) => {
  const response = await request.get("/api/ai-industry-panorama");
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toMatch(/application\/json/);
  const payload = await response.json();

  expect(Object.keys(payload).sort()).toEqual([
    "entities",
    "evidence",
    "facets",
    "ok",
    "relationships",
    "release",
    "schema_version",
    "sources",
    "taxonomy",
  ]);
  expect(payload).toMatchObject({
    ok: true,
    schema_version: "ai_industry_panorama_public.v1",
    release: {
      release_id: expect.stringMatching(/^ai-industry-panorama\./),
      taxonomy_version: expect.stringMatching(/^ai-industry-panorama-taxonomy\./),
      evidence_cutoff: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      review_state: "published",
    },
  });
  expect(payload.taxonomy.length).toBeGreaterThanOrEqual(6);
  expect(payload.entities.length).toBeGreaterThanOrEqual(35);
  expect(payload.relationships.length).toBeGreaterThanOrEqual(45);
  expect(payload.sources.length).toBeGreaterThan(0);
  expect(payload.evidence.length).toBeGreaterThan(0);

  const entityIds = new Set(payload.entities.map((entity: { entity_id: string }) => entity.entity_id));
  const assertionIds = new Set<string>();
  const evidenceIds = new Set(payload.evidence.map((item: { evidence_id: string }) => item.evidence_id));
  for (const relationship of payload.relationships) {
    expect(entityIds.has(relationship.source_entity_id)).toBe(true);
    expect(entityIds.has(relationship.target_entity_id)).toBe(true);
    expect(relationship.assertion_id).toBeTruthy();
    expect(assertionIds.has(relationship.assertion_id)).toBe(false);
    assertionIds.add(relationship.assertion_id);
    expect(relationship.evidence_ids.length + relationship.premise_assertion_ids.length).toBeGreaterThan(0);
    for (const evidenceId of relationship.evidence_ids) {
      expect(evidenceIds.has(evidenceId)).toBe(true);
    }
  }
  expect(assertionIds.size).toBe(payload.relationships.length);

  const anchors = payload.entities.filter((entity: { is_demand_anchor: boolean }) => entity.is_demand_anchor);
  expect(anchors).toHaveLength(6);
  const forward = new Map<string, Set<string>>();
  for (const relationship of payload.relationships) {
    if (!forward.has(relationship.source_entity_id)) {
      forward.set(relationship.source_entity_id, new Set());
    }
    forward.get(relationship.source_entity_id)!.add(relationship.target_entity_id);
  }
  for (const anchor of anchors) {
    const firstHop = forward.get(anchor.entity_id) ?? new Set<string>();
    expect(firstHop.size).toBeGreaterThan(0);
    const secondHop = new Set(
      [...firstHop].flatMap((entityId) => [...(forward.get(entityId) ?? [])]),
    );
    expect(secondHop.size).toBeGreaterThan(0);
  }

  const forbiddenKeys = new Set([
    "api_key",
    "authorization",
    "credential",
    "curator",
    "database_url",
    "internal_notes",
    "order",
    "password",
    "portfolio",
    "position",
    "private_key",
    "raw_source",
    "reviewer",
    "secret",
    "token",
    "user_insight",
  ]);
  const visit = (value: unknown): void => {
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    if (!value || typeof value !== "object") return;
    for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
      expect(forbiddenKeys.has(key.toLowerCase())).toBe(false);
      visit(nested);
    }
  };
  visit(payload);

  const sensitiveQueryNames = new Set([
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "client_secret",
    "credential",
    "password",
    "private_key",
    "secret",
    "signature",
    "token",
  ]);
  for (const source of payload.sources) {
    const parsed = new URL(source.url);
    expect(parsed.protocol).toBe("https:");
    expect(parsed.username).toBe("");
    expect(parsed.password).toBe("");
    for (const name of parsed.searchParams.keys()) {
      expect(sensitiveQueryNames.has(name.toLowerCase())).toBe(false);
    }
  }
});
