/**
 * Real-browser SSE through the Next.js /api proxy: Browser -> Next.js -> FastAPI -> Redis.
 *
 * Needs an isolated stack: PLAYWRIGHT_BASE_URL (Next.js), and E2E_REDIS_URL pointing at
 * that stack's Redis (used to publish test events and read connection slots). Skipped otherwise.
 */
import net from "node:net";
import { test, expect, type Browser, type Page } from "@playwright/test";

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000";
const REDIS_URL = process.env.E2E_REDIS_URL;

test.describe.configure({ mode: "serial" });
test.skip(!REDIS_URL, "E2E_REDIS_URL not set (needs an isolated stack)");

type Reply = string | number | null;

/** Minimal RESP client: one command per connection; integer, simple, error and bulk replies. */
function redis(...args: string[]): Promise<Reply> {
  const url = new URL(REDIS_URL!);
  const db = url.pathname.replace("/", "") || "0";
  const commands = [["SELECT", db], args];
  const wire = commands
    .map((cmd) => `*${cmd.length}\r\n` + cmd.map((a) => `$${Buffer.byteLength(a)}\r\n${a}\r\n`).join(""))
    .join("");
  return new Promise((resolve, reject) => {
    const sock = net.createConnection(Number(url.port || 6379), url.hostname);
    let buf = "";
    const replies: Reply[] = [];
    sock.on("error", reject);
    sock.on("data", (chunk) => {
      buf += chunk.toString("utf8");
      while (buf.length) {
        const end = buf.indexOf("\r\n");
        if (end < 0) return;
        const kind = buf[0];
        const head = buf.slice(1, end);
        if (kind === "$") {
          const len = Number(head);
          if (len < 0) {
            replies.push(null);
            buf = buf.slice(end + 2);
          } else {
            if (buf.length < end + 2 + len + 2) return;
            replies.push(buf.slice(end + 2, end + 2 + len));
            buf = buf.slice(end + 2 + len + 2);
          }
        } else {
          if (kind === "-") return reject(new Error(head));
          replies.push(kind === ":" ? Number(head) : head);
          buf = buf.slice(end + 2);
        }
        if (replies.length === commands.length) {
          sock.end();
          resolve(replies[replies.length - 1]);
        }
      }
    });
    sock.write(wire);
  });
}

async function liveSlots(teamId: string): Promise<number> {
  return Number(await redis("ZCOUNT", `heliox:events:conn_leases:${teamId}`, String(Date.now() / 1000), "+inf"));
}

async function waitForSlots(teamId: string, expected: number, timeoutMs = 8000): Promise<number> {
  const deadline = Date.now() + timeoutMs;
  let slots = await liveSlots(teamId);
  while (slots !== expected && Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 200));
    slots = await liveSlots(teamId);
  }
  return slots;
}

async function publish(teamId: string, eventType = "budget.warning") {
  const eventId = `evt_e2e_${Math.random().toString(16).slice(2, 14)}`;
  const payload = JSON.stringify({
    event_id: eventId,
    event_type: eventType,
    team_id: teamId,
    payload: { probe: eventId },
    timestamp: new Date().toISOString(),
  });
  const receivers = await redis("PUBLISH", `heliox:events:${teamId}`, payload);
  return { eventId, receivers: Number(receivers), publishedAt: Date.now() };
}

/** Register and log in through the proxy; the session cookie lands on the app origin. */
async function newTenant(browser: Browser, tag: string) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const email = `sse-${tag}-${Date.now()}-${Math.random().toString(16).slice(2, 6)}@example.com`;
  const password = `Sse-${Math.random().toString(36).slice(2)}-Pw1!`;
  const reg = await page.request.post(`${BASE_URL}/api/v1/auth/register`, {
    data: { email, password, full_name: `SSE ${tag}` },
  });
  expect(reg.ok()).toBeTruthy();
  const login = await page.request.post(`${BASE_URL}/api/v1/auth/login`, { form: { username: email, password } });
  expect(login.status()).toBe(200);
  const teams = await page.request.get(`${BASE_URL}/api/v1/teams`);
  expect(teams.status()).toBe(200);
  const teamId: string = (await teams.json())[0].id;
  return { context, page, teamId, email, password };
}

/** Open an EventSource in the page and record what arrives. */
async function openStream(page: Page, name: string) {
  await page.evaluate((key) => {
    const w = window as unknown as { __sse: Record<string, unknown> };
    w.__sse = w.__sse || {};
    const rec = { opens: 0, errors: 0, events: [] as unknown[] };
    const es = new EventSource("/api/v1/events/stream", { withCredentials: true });
    es.onopen = () => rec.opens++;
    es.onerror = () => rec.errors++;
    es.addEventListener("budget.warning", (e) => {
      const m = e as MessageEvent;
      rec.events.push({ id: m.lastEventId, type: m.type, data: m.data, at: Date.now() });
    });
    w.__sse[key] = { es, rec };
  }, name);
}

async function streamState(page: Page, name: string) {
  return page.evaluate((key) => {
    const w = window as unknown as { __sse: Record<string, { es: EventSource; rec: unknown }> };
    const s = w.__sse[key];
    return { readyState: s.es.readyState, ...(s.rec as object) } as {
      readyState: number;
      opens: number;
      errors: number;
      events: { id: string; type: string; data: string; at: number }[];
    };
  }, name);
}

async function closeStream(page: Page, name: string) {
  await page.evaluate((key) => {
    const w = window as unknown as { __sse: Record<string, { es: EventSource }> };
    w.__sse[key].es.close();
  }, name);
}

test("authenticated stream delivers events immediately, intact and tenant-scoped", async ({ browser }) => {
  const a = await newTenant(browser, "a");
  const b = await newTenant(browser, "b");
  await a.page.goto(`${BASE_URL}/login`);
  await b.page.goto(`${BASE_URL}/login`);

  await openStream(a.page, "main");
  await expect.poll(async () => (await streamState(a.page, "main")).opens, { timeout: 10000 }).toBe(1);
  expect(await waitForSlots(a.teamId, 1)).toBe(1);

  await openStream(b.page, "main");
  await expect.poll(async () => (await streamState(b.page, "main")).opens, { timeout: 10000 }).toBe(1);

  const sent = await publish(a.teamId);
  expect(sent.receivers).toBeGreaterThanOrEqual(1);
  await expect.poll(async () => (await streamState(a.page, "main")).events.length, { timeout: 5000 }).toBe(1);
  const [event] = (await streamState(a.page, "main")).events;
  const latencyMs = event.at - sent.publishedAt;
  console.log(`SSE event latency through proxy: ${latencyMs} ms`);
  expect(latencyMs).toBeLessThan(2000); // well under the 30 s heartbeat
  expect(event.id).toBe(sent.eventId);
  expect(event.type).toBe("budget.warning");
  expect(JSON.parse(event.data)).toMatchObject({ event_id: sent.eventId, team_id: a.teamId, payload: { probe: sent.eventId } });

  // Tenant B never sees tenant A's event
  await new Promise((r) => setTimeout(r, 1000));
  expect((await streamState(b.page, "main")).events).toEqual([]);

  // Closing the EventSource releases the backend slot
  const closedAt = Date.now();
  await closeStream(a.page, "main");
  expect(await waitForSlots(a.teamId, 0)).toBe(0);
  console.log(`slot released ${Date.now() - closedAt} ms after EventSource.close()`);

  await a.context.close();
  await b.context.close();
});

test("open/close cycles and page navigation do not leak slots", async ({ browser }) => {
  const t = await newTenant(browser, "cycles");
  await t.page.goto(`${BASE_URL}/login`);
  for (let i = 0; i < 8; i++) {
    await openStream(t.page, `c${i}`);
    await expect.poll(async () => (await streamState(t.page, `c${i}`)).opens, { timeout: 10000 }).toBe(1);
    await closeStream(t.page, `c${i}`);
  }
  expect(await waitForSlots(t.teamId, 0)).toBe(0);

  // Authenticated pages open the NotificationBell stream; navigating must not accumulate streams
  for (const path of ["/", "/analytics", "/budgets", "/alerts", "/reports", "/settings", "/"]) {
    await t.page.goto(`${BASE_URL}${path}`, { waitUntil: "domcontentloaded" });
    await t.page.waitForTimeout(1500);
    expect(await liveSlots(t.teamId)).toBeLessThanOrEqual(2);
  }
  await t.page.goto("about:blank");
  expect(await waitForSlots(t.teamId, 0)).toBe(0);

  // Still able to connect afterwards
  await t.page.goto(`${BASE_URL}/login`);
  await openStream(t.page, "after");
  await expect.poll(async () => (await streamState(t.page, "after")).opens, { timeout: 10000 }).toBe(1);
  await t.context.close();
});

test("multiple tabs obey the five-connection limit and free slots on close", async ({ browser }) => {
  const t = await newTenant(browser, "tabs");
  const tabs: Page[] = [];
  for (let i = 0; i < 6; i++) {
    const tab = await t.context.newPage();
    await tab.goto(`${BASE_URL}/login`);
    await openStream(tab, "s");
    tabs.push(tab);
    await tab.waitForTimeout(400);
  }
  expect(await waitForSlots(t.teamId, 5)).toBe(5);
  const states = await Promise.all(tabs.map((tab) => streamState(tab, "s")));
  expect(states.filter((s) => s.opens >= 1).length).toBe(5);
  expect(states[5].opens).toBe(0); // the sixth was refused (429), not silently admitted

  for (const tab of tabs) await tab.close();
  expect(await waitForSlots(t.teamId, 0)).toBe(0);
  await t.context.close();
});

test("a stream interrupted by the server reconnects and keeps receiving", async ({ browser }) => {
  const t = await newTenant(browser, "reconnect");
  await t.page.goto(`${BASE_URL}/login`);
  await openStream(t.page, "r");
  await expect.poll(async () => (await streamState(t.page, "r")).opens, { timeout: 10000 }).toBe(1);

  // Drop the API's Redis subscription: the server ends the stream, the browser retries after 5 s
  await redis("CLIENT", "KILL", "TYPE", "pubsub");
  await expect.poll(async () => (await streamState(t.page, "r")).opens, { timeout: 20000 }).toBe(2);
  const sent = await publish(t.teamId);
  await expect
    .poll(async () => (await streamState(t.page, "r")).events.map((e) => e.id), { timeout: 5000 })
    .toContain(sent.eventId);
  await closeStream(t.page, "r");
  expect(await waitForSlots(t.teamId, 0)).toBe(0);
  await t.context.close();
});

test("JSON endpoints, error statuses and logout still work through the proxy", async ({ browser }) => {
  const t = await newTenant(browser, "json");
  const teams = await t.page.request.get(`${BASE_URL}/api/v1/teams`);
  expect(teams.status()).toBe(200);
  expect(teams.headers()["content-type"]).toContain("application/json");
  const missing = await t.page.request.get(`${BASE_URL}/api/v1/jobs/00000000-0000-0000-0000-000000000000`);
  expect(missing.status()).toBe(404);

  const logout = await t.page.request.post(`${BASE_URL}/api/v1/auth/logout`);
  expect(logout.status()).toBe(200);
  expect((await t.page.request.get(`${BASE_URL}/api/v1/teams`)).status()).toBe(401);
  const unauthStream = await t.page.request.get(`${BASE_URL}/api/v1/events/stream`);
  expect(unauthStream.status()).toBe(401);
  await t.context.close();
});
