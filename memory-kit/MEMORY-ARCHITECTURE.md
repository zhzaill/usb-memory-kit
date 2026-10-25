# memory-kit 记忆架构

来源原则：[CJackHwang/ds2api](https://github.com/CJackHwang/ds2api)（参考 commit `8316cf8a0352e900e03ce600b792083f590d80e2`）。
本项目没有引入 DeepSeek 账号、PoW 或上游网页协议，只借鉴其架构边界。

## 1. 分层

```text
HTTP / MCP payload
    -> protocol adapter
    -> MemoryQuery / MemoryTurn
    -> shared memory core
    -> protocol-neutral result
    -> HTTP / MCP renderer
```

长期记忆仍是 `corpus -> chunks -> vectors -> organization` 的不可变派生物。
事实源仍是各机器原位日志；`memory-kit` 中的 `corpus` 和 `index` 可随时重建。

## 2. 与 ds2api 的对应关系

| ds2api 原则 | memory-kit 实现 |
|---|---|
| OpenAI/Claude/Gemini adapter 只做协议边界 | HTTP GET/POST 与 MCP 参数先归一成 `MemoryQuery` / `MemoryTurn` |
| 所有协议共用 completion core | 所有入口共用 `KitIndex.search`，不复制检索算法 |
| 服务器端 chat history | `state\sessions\<owner-hash>\*.json`，有 revision、TTL、条数上限 |
| 长上下文转 `DS2API_HISTORY.txt` | `MEMORY_CONTEXT.md` 上下文包，限制字符预算 |
| response TTL store，按 caller 隔离 | 内存中的 `ctx_*` 缓存，按 owner 隔离，默认 TTL 900 秒 |
| 配置热加载与严格校验 | `config\kit.json` 的 `memory` 段，非法查询在入口拒绝 |

## 3. 记忆类型

- **长期记忆**：日志块、向量、社区。只读，重建幂等。
- **工作记忆**：会话轮次，可写，按 owner 隔离，有 TTL 和条数上限。
- **上下文包**：针对一次查询把工作记忆与长期记忆压缩成 `MEMORY_CONTEXT.md`。

工作记忆不是事实源，也不替代原始日志目录。需要长期保留的结论仍应写回日志。

## 4. HTTP

兼容旧接口：

```text
GET  /api/search?q=...
GET  /api/clusters
GET  /api/recent
```

新增标准入口（`/v1/memory/*` 是 `/api/*` 的别名）：

```text
POST   /api/search
POST   /api/sessions
GET    /api/sessions?owner=default
GET    /api/sessions/{id}?owner=default
POST   /api/sessions/{id}/turns
DELETE /api/sessions/{id}?owner=default
POST   /api/context
GET    /api/context/{id}?owner=default
```

## 5. MCP

- `search_memory`
- `recent_logs`
- `clusters`
- `kit_about`
- `create_memory_session`
- `append_memory_turn`
- `session_history`
- `memory_context`
- `get_memory_context`

## 6. 安全边界

- 服务默认只监听 `127.0.0.1`，不是多租户公网服务。
- `owner` 用于逻辑隔离和防误取，不等同于鉴权。
- 上下文缓存仅存在于进程内，重启即失效。
- 会话文件落在 U 盘 `state\sessions\`，外借 U 盘前应清理。
- 不记录 API key、密码或其他凭据。
