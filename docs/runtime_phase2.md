# Runtime Phase 2 — 可用性升级（状态清晰化）

本文档面向最终用户和协作者，补充 Phase 1.5 之后的可用性改进说明。

---

## 核心改进：两种状态的区分

Phase 2 最重要的改进是明确区分了：

| 概念 | 说明 |
|---|---|
| **当前生效的 Runtime（Active Runtime）** | 系统正在使用的那套配置，从上次保存或 Reset 后的状态 |
| **编辑中的表单（Editing Form）** | 你正在修改但尚未保存的值 |

这两者可以不同步。例如：你可以修改表单但还没点 Save，此时 Active Runtime 仍然是上一次保存的状态，而表单已经变了。

---

## Active Status Banner

设置面板顶部的 **Currently Active** 区域实时展示：

- 当前是否启用自定义 runtime（`Custom Active` vs `Default Runtime`）
- 当前生效的 Provider / Base URL / Model / API Key 状态
- 不受表单编辑影响，只有保存或 Reset 后才会变化

这解决了"我保存的值到底有没有生效"的困惑。

---

## Unsaved Changes 提示

当表单有未保存的更改时：

- 设置面板标题旁会显示 **Unsaved changes** 标签（黄色）
- 表单边框变为橙色（提示这些字段还没有被持久化）
- **Save & Activate** 按钮变为可点击状态
- 关闭面板时，标题变为 **Cancel (changes discarded)**

保存成功后，dirty 状态自动清除。

---

## Test Connection 的行为

**Test Connection 只验证连通性，不代表保存了配置。**

- 点击后发送一次最小请求（`invoke("hi")`）验证 endpoint 可达
- 结果分为以下几种：

  | 状态 | 含义 | 前端显示 |
  |---|---|---|
  | `Connection OK` | 验证成功 | 绿色 ✓ |
  | `Failed — auth_failure` | API Key 无效（401） | 红色 ✗ |
  | `Failed — invalid_url` | Base URL 格式不合法 | 红色 ✗ |
  | `Failed — network_error` | 域名无法解析/连接被拒绝 | 红色 ✗ |
  | `Failed — timeout` | 连接超时 | 红色 ✗ |
  | `Failed — model_not_found` | 模型在 endpoint 上不可用 | 红色 ✗ |

- 结果会保留在面板上，直到你再次修改表单或 Reset
- **测试连接不等于保存配置**（两条独立路径）

---

## Save & Activate

点击 **Save & Activate** 后：

1. 表单值被持久化到 `data/active_runtime.json`
2. 环境变量 `LLM_API_KEY` / `LLM_RUNTIME_BASE_URL` 立即更新
3. 运行时 registry 缓存失效
4. **立即生效**：后续所有请求都走新的 runtime

成功提示：`Configuration saved and now active. Changes take effect immediately.`

---

## Reset 的行为

点击 **Reset** 后：

1. 持久化配置被覆盖为 `enabled=False` 的默认值
2. `LLM_API_KEY` / `LLM_RUNTIME_BASE_URL` 环境变量被清除
3. Registry 缓存失效
4. 系统回退到默认 runtime（MockLLM fallback）

**Reset 不只是清空输入框**——它真实改变了系统行为。

成功提示：`Configuration cleared. System now uses default runtime (no custom endpoint).`

---

## Fallback 逻辑

当自定义 runtime 不可用时，系统自动降级到 MockLLM：

- 连接超时 → MockLLM
- 认证失败 → MockLLM
- 网络不通 → MockLLM

这保证了系统不会因为 runtime 配置错误而完全不可用。

---

## 当前限制（Phase 2 仍不包含）

- 不支持多 Provider（仅 `openai_compatible`）
- 不支持 Profile 管理（每次只保存一组配置）
- API Key 以明文存储在项目本地 JSON 文件中（不适用于多用户/共享部署）
- 不支持 Provider Registry UI
- Test Connection 不做真正的推理调用，只是连通性验证

---

## 文件索引

| 文件 | 说明 |
|---|---|
| `app/runtime/active_config.py` | 配置持久化逻辑 |
| `app/api/routes.py` | `test` / `reset` / PUT `runtime-config` 端点 |
| `app/api/schemas.py` | Pydantic schema（含 `RuntimeConfigTestResponse`） |
| `frontend/src/features/settings/store.ts` | 前端状态管理（含 dirty state） |
| `frontend/src/features/settings/settings-view.tsx` | 设置页 UI（含 Active Status Banner） |
| `data/active_runtime.json` | 配置持久化文件（gitignored） |
