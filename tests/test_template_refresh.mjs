import assert from "node:assert/strict";
import fs from "node:fs";

const template = fs.readFileSync(new URL("../src/template-dashboard-v1.3.0.html", import.meta.url), "utf8");
const match = template.match(/const NETWORK_RETRY_DELAYS_MS = \[800, 1600\];[\s\S]*?(?=\naiBtn\.addEventListener)/);
assert.ok(match, "未找到刷新重试函数");
const loadRefreshHelper = new Function(`${match[0]}; return { NETWORK_RETRY_DELAYS_MS, fetchDashboardData };`);
const { NETWORK_RETRY_DELAYS_MS, fetchDashboardData } = loadRefreshHelper();

assert.deepEqual(NETWORK_RETRY_DELAYS_MS, [800, 1600]);

{
  let calls = 0;
  const delays = [];
  const result = await fetchDashboardData(
    async () => {
      calls += 1;
      if (calls < 3) throw new TypeError("Failed to fetch");
      return { ok: true, json: async () => ({ ok: true }) };
    },
    async delay => { delays.push(delay); },
  );
  assert.equal(calls, 3);
  assert.deepEqual(delays, [800, 1600]);
  assert.deepEqual(result, { ok: true });
}

{
  let calls = 0;
  await assert.rejects(
    fetchDashboardData(
      async () => {
        calls += 1;
        return { ok: false, status: 500, json: async () => ({ error: "Base 权限错误" }) };
      },
      async () => {},
    ),
    /Base 权限错误/,
  );
  assert.equal(calls, 1, "HTTP／Base 错误不应按网络断连重试");
}

{
  let calls = 0;
  await assert.rejects(
    fetchDashboardData(
      async () => {
        calls += 1;
        throw new TypeError("Failed to fetch");
      },
      async () => {},
    ),
    /自动重试2次仍未恢复/,
  );
  assert.equal(calls, 3);
}

console.log("template refresh retry tests passed");
