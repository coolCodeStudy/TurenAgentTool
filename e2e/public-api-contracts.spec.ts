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

async function readDailyMutationState(request: APIRequestContext) {
  const [historyJobsResponse, cnDatesResponse] = await Promise.all([
    request.get("/api/daily-market-brief/history-jobs"),
    request.get("/api/daily-market-brief/dates?market=CN"),
  ]);

  expect(historyJobsResponse.status()).toBe(200);
  expect(cnDatesResponse.status()).toBe(200);

  const [historyJobs, cnDates] = await Promise.all([
    historyJobsResponse.json(),
    cnDatesResponse.json(),
  ]);

  return {
    historyJobIds: historyJobs.jobs.map((job: { id: number }) => job.id),
    cnSavedDates: cnDates.dates,
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
