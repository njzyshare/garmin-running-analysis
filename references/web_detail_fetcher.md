---
title: "网页端计圈数据获取（备用方案）"
summary: "通过 Playwright 自动化高驰 Training Hub 网页端，绕过 MCP 接口限制获取详细计圈数据；headless 后台运行不弹窗；登录态独立存放便于 skill 共享"
---

> 此文件适用于高驰平台，Garmin 可通过 API 直接获取同类数据，仅供参考

# 网页端计圈数据获取（备用方案）

## 一、为什么需要这个方案

**问题：** MCP 工具的"最快单圈"实际是"最快1公里段"（任意 1km 段的最快配速），**不是**计圈表里"最快"标记的那一圈。

| 数据源 | 字段 | 真实含义 |
|--------|------|---------|
| 高驰 APP | 最快单圈 | 所有计圈中配速最快的一圈（被标"最快"） |
| 高驰 网页端 "概要" | 最快1公里 | 任意 1km 段的最快配速（**不一定是计圈**） |
| MCP `getActivityDetail` | 最快单圈 | 实际 = 网页端的"最快1公里" |

**实证：**
- 5/27「400米间歇8组」：APP 最快 3:45/km，网页端/MCP 最快 4:36/km
- 6/4「间歇800×8」：APP 最快 3:51/km，网页端/MCP 最快 4:16/km

**后果：** 用 MCP"最快单圈"评估间歇质量 = 错误指标。

**解法：** 用 Playwright 打开 `t.coros.com`，抓取活动详情页的**计圈表**——表中"最快"标记的那一行才是真正的"最快单圈"。

---

## 二、方案原理

- 高驰网页端 `https://t.coros.com/activity-detail?labelId={id}&sportType={type}` 有完整计圈表
- MCP token scope 是 `mcp.tools`，**无法**调网页端 GraphQL API（403 Forbidden）
- 用浏览器自动化 + 已保存的登录态（`storageState`），完整复现登录后的页面数据
- **headless 模式**：浏览器不弹窗到前台，不打扰用户

---

## 三、文件存放约定（重要）

**登录态独立存放于工作区，不进 skill 目录：**

```
{workspace}/高驰数据分析/                           ← 工作区数据目录
├── coros_web_login.js                              ← 登录脚本（首次会弹窗）
├── coros_detail.js                                 ← 抓取器（始终 headless）
└── .secrets/                                       ← 个人数据目录（与 skill 分离）
    ├── _user_running_profile.md                    ← 个人档案
    ├── coros-mcp-token-backup.json                 ← MCP token 备份
    └── coros-state/
        └── coros_state.json                        ← Playwright storageState（登录态）
```

**为什么不放 skill 目录？**
- skill 可共享给其他人（用户预期）
- 登录态是个人凭据，绝对不能随 skill 一起分发
- 与 MCP token 存放位置一致

> 镜像 MCP 的设计：MCP 同样把 token 存于 `~/.workbuddy/.tmp/node_modules/corOs-cache/cn/token.json`，不在 skill 目录。

---

## 四、一次性环境准备

### 4.1 安装 Playwright + Chromium

```bash
# 安装 Playwright 包到工作区（项目级 node_modules）
# 🚩 使用当前环境的 node 和 npm，路径自动适配
cd $WORKSPACE
npm install playwright

# 安装 Chromium（首次约 180MB）
npx playwright install chromium
```

### 4.2 一次性登录（仅此一步会弹窗）

```bash
cd {workspace}/高驰数据分析
node coros_web_login.js
```

- 浏览器弹窗 → 用户手动登录 → 脚本检测跳转 → 自动保存 `.secrets/coros-state/coros_state.json` → 关闭浏览器
- **整个过程只在首次需要用户介入**；之后 headless 模式完全无感

**登录态有效期：** 数月（高驰 token 通常 90 天+），过期再重跑一次。

---

## 五、headless 后台化（关键）

### 5.1 启动方式

```javascript
const browser = await chromium.launch({
  headless: true,           // ✅ 不弹窗到前台
  args: [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-gpu',
  ],
});

const context = await browser.newContext({
  storageState: STATE_FILE,  // 直接复用登录态，无需用户交互
  locale: 'zh-CN',
});
const page = await context.newPage();
```

### 5.2 等页面就绪的稳定模式

```javascript
// ❌ networkidle 经常超时（页面有持续的后台轮询）
await page.goto(url, { waitUntil: 'networkidle' });

// ✅ domcontentloaded + 关键元素等待
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
await page.waitForTimeout(5000);
try {
  await page.waitForSelector('text=平均配速', { timeout: 15000 });
} catch (e) {
  // 继续抓取
}
```

### 5.3 抓取计圈表

```javascript
const tables = await page.evaluate(() => {
  const result = [];
  document.querySelectorAll('table').forEach((t, i) => {
    const rows = Array.from(t.querySelectorAll('tr')).map(r =>
      Array.from(r.querySelectorAll('th,td')).map(c => (c.textContent || '').trim())
    );
    result.push({ idx: i, rows });
  });
  return result;
});
```

**计圈表特征：** 第一个 `table`，列头为「圈数 / 距离 / 时间 / 累计时间 / 平均配速 / 平均心率 / 等强配速 / 达标率」。

**"最快"标记：** 在该 table 的某一行中，第一列文字是 "最快"（不是圈号），这一行的平均配速就是 APP 显示的"最快单圈"。

---

## 六、登录态失效处理（重要约定）

**核心原则：抓取脚本永远不在运行时自动弹窗。**

| 场景 | 行为 |
|------|------|
| 登录态有效 + 页面正常 | ✅ 返回数据，浏览器不弹窗 |
| 登录态文件不存在 | 抛 `NoLoginStateError`，错误信息提示运行 `coros_web_login.js` |
| 登录态过期 / 失效（被重定向到 /auth） | 返回 `loginRequired: true`，不抛异常，**不弹窗** |
| 抓取遇到其他错误 | 抛对应错误，**不弹窗** |

**为什么不在登录失效时弹窗？**
- 用户明确要求：浏览器操作尽量后台化，不干扰工作
- 自动弹窗会让 Playwright 切换浏览器焦点，中断用户正在做的事
- 用户主动跑登录脚本的成本 < 被干扰的体验成本

**调用方处理：**

```javascript
try {
  const { fetchActivityDetail } = require('./coros_detail.js');
  const data = await fetchActivityDetail(labelId, sportType);

  if (data.loginRequired) {
    console.log('⚠️  登录态已失效，请运行：node coros_web_login.js');
    return;
  }
  // 正常处理 data
} catch (e) {
  if (e.code === 'NO_LOGIN_STATE') {
    console.log('⚠️  ' + e.message);
  } else {
    throw e;
  }
}
```

---

## 七、模块化脚本 API

```javascript
const {
  fetchActivityDetail,   // 抓取单次活动详情
  listActivities,        // 列出最近活动
  parseLaps,             // 解析计圈表
  NoLoginStateError,     // 登录态缺失错误类
  STATE_FILE,            // 登录态文件路径
  STATE_DIR,             // 登录态目录路径
} = require('./coros_detail.js');
```

### fetchActivityDetail(labelId, sportType)

```javascript
const data = await fetchActivityDetail('477970836232372427', '100');
// 返回：
// {
//   summary: { 距离: '10.40', 平均配速: "05'10\"", ... },
//   tables: [ [{圈数, 距离, 时间, ...}], ... ],
//   url: 'https://t.coros.com/activity-detail?...',
//   loginRequired: false,
// }
```

### listActivities(limit = 30)

```javascript
const { activities, loginRequired } = await listActivities(50);
// activities: [{ name, labelId, sportType, href }, ...]
// loginRequired: true 表示需要重新登录
```

### parseLaps(data)

```javascript
const { laps, fastestLap } = parseLaps(data);
// laps: 全部计圈（含 marker='最快' / ''）
// fastestLap: 被标"最快"的那一圈对象 { marker, number, distance, time, pace, hr, ... }
```

---

## 八、活动列表 URL 规律

| 类型 | URL |
|------|-----|
| 仪表盘 | `https://t.coros.com/admin/views/dash-board` |
| 活动列表 | `https://t.coros.com/admin/views/activities` |
| 活动详情 | `https://t.coros.com/activity-detail?labelId={id}&sportType={type}` |
| 数据分析 | `https://t.coros.com/admin/views/data-analysis` |

**sportType 代码：**
- 100 = Outdoor Run（户外跑）
- 102 = Trail Run（越野跑）
- 104 = Hike（徒步）
- 402 = Strength Training（力量训练）
- 900 = Walk（健走）

---

## 九、CLI 用法

```bash
# 列出最近活动
node coros_detail.js --list

# 抓取单次活动
node coros_detail.js <labelId> <sportType>
```

**未登录时输出示例：**
```
⚠️  未找到登录态文件。
请先运行登录脚本（会自动弹窗一次，登录后即可）：
  node coros_web_login.js

登录态文件位置：{workspace}/高驰数据分析/.secrets/coros-state/coros_state.json
```

---

## 十、何时使用这个方案

✅ **使用场景：**
- 分析间歇训练质量（400m / 800m / 1000m × N）
- 需要真实的"最快单圈"（APP 口径）
- MCP"最快单圈"与 APP 显示不一致需要核实
- 任何需要"被标最快的那一圈配速"的场景

❌ **不需要这个方案：**
- 日常训练汇总分析（用 MCP `getActivityDetail`）
- 训练负荷、睡眠、HRV 趋势（MCP 标准工具）
- 教练式文字诊断（用 MCP `analyzeActivityDetail`）

---

## 十一、常见问题

**Q1: 登录态过期怎么办？**
A: 删除 `.secrets/coros-state/coros_state.json`，重跑 `node coros_web_login.js`，重新手动登录一次。

**Q2: 抓不到计圈表？**
A: 1) 检查登录态是否过期；2) 把 `waitForTimeout` 调到 8000；3) 用 `page.content()` 保存 HTML 排查。

**Q3: headless 模式报 "Chromium sandbox failed"？**
A: 加上 `--no-sandbox --disable-setuid-sandbox --disable-gpu` 三个参数。

**Q4: 是否能完全无感（不弹窗、不抢焦点）？**
A: 可以。`headless: true` 模式下浏览器在内存中运行，**不会**出现在任务栏/前台。

**Q5: 抓取速度？**
A: 单次活动详情 5-10 秒（headless 模式），完全可接受。

**Q6: 共享 skill 时登录态会泄露吗？**
A: 不会。登录态和所有个人数据独立存于 `.secrets/` 目录，**不会**随 skill 文件一起分发。共享前请确认：
- ✅ 打包的目录里不包含 `.secrets/`
- ✅ `SKILL.md` / `references/` / `scripts/` 是干净的

**Q7: 我希望把 skill 共享给跑友用，他需要做什么？**
A: 1) 复制 skill 目录给他；2) 跑友先在 `{workspace}/高驰数据分析/` 下创建 `.secrets/` 目录；3) 跑友自己执行 `node coros_web_login.js` 完成一次登录（会弹窗）；4) 登录态会保存到他自己的 `.secrets/coros-state/` 里。
