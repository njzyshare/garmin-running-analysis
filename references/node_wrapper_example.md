> 此文件适用于高驰平台，Garmin 可通过 API 直接获取同类数据，仅供参考

# Node 包装调用示例

当 `coros-mcp call-tool --arguments-json ...` 在 PowerShell 里因为 JSON 转义失败时，优先用 Node 包装调用。

示例：

```powershell
@'
const { spawnSync } = require('child_process');
const path = require('path');

const cli = path.resolve('.tmp/coros-mcp-local/node_modules/coros-mcp/dist/cli.js');
const cacheRoot = path.resolve('.tmp/coros-cache');

function callTool(tool, args) {
  const result = spawnSync(process.execPath, [
    cli,
    '--cache-root', cacheRoot,
    'call-tool',
    '--tool', tool,
    '--arguments-json', JSON.stringify(args),
  ], { encoding: 'utf8' });

  if (result.status !== 0) {
    throw new Error(result.stderr || result.stdout);
  }

  return JSON.parse(result.stdout);
}

const data = callTool('querySportRecords', {
  startDate: '20260501',
  endDate: '20260514',
  sportTypeCodes: [65535],
  minDistanceKm: 0,
  maxDistanceKm: 9999,
  minDurationMinutes: 0,
  maxDurationMinutes: 100000,
  maxAveragePace: '99:59',
  locationKeyword: '',
  limit: 100,
  timezone: 'Asia/Shanghai',
});

process.stdout.write(JSON.stringify(data, null, 2));
'@ | node -
```

适合以下带参数工具：

- `querySportRecords`
- `queryTrainingLoadAssessment`
- `queryHrvAssessment`
- `queryRestingHeartRate`
- 其他任何需要 `--arguments-json` 的 COROS 工具
