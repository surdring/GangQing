# IT/OT 跨网域安全交互规范（Cross-Domain Security）

本文件固化 GangQing（钢擎）在 IT 与 OT 跨域交互时的网络分区、数据流向、写入门禁与验收口径。目标是保证“数据可用、控制可控、风险可隔离”。

## 0. 强制原则
- **禁止 AI 服务直连 OT 写接口**：不得出现后端直接调用 DCS/PLC 写 API 的路径。
- **默认只读**：OT 侧任何写入必须走草案/审批/白名单/Kill Switch/OT 二次确认闭环。
- **物理/逻辑分区**：IT、DMZ、OT 分区清晰，跨区必须有边界设备与审计。

## 1. 网络分区建议
- IT 区：GangQing Web/Backend、业务数据库、检索与模型推理
- DMZ 区：跨域代理、消息中转、审计汇聚（可选）
- OT 区：DCS/PLC、OPC UA Server、采集机、执行网关（OT 侧）

## 2. 数据流（只读）
推荐模式（对齐 TDD）：
- OT 数据（DCS） -> OT 前置采集机 -> 单向网闸/数据二极管 -> IT 消息队列/时序库 -> GangQing

验收口径：
- IT 侧可以查询 OT 数据（只读），但不能产生反向控制链路。

## 3. 控制流（写入/下发）
强制模式：
- GangQing 仅生成草案 + 提交审批
- 经审批后由 **Execution Gateway**（执行网关）受控下发
- OT 侧必须二次确认（`ot_operator`）并形成可复核记录

## 4. Execution Gateway（执行网关）要求
- 白名单：设备/点位/操作类型必须在白名单内
- 阈值限制：变化率/范围/次数限制
- 幂等：必须有 idempotency key 或 executionId
- 超时/重试：可配置，失败必须可审计
- Kill Switch：熔断开启时必须拒绝执行

## 5. 审计与证据链
- 跨域读写必须写审计（至少包含 `requestId/tenantId/projectId`）。
- OT 写入必须记录：变更前值、变更后值、生效时间、确认人、executionId。

## 6. 最小验收用例
- 只读查询 OT 数据：可用。
- 尝试从 IT 侧直接写 OT：必须拒绝并审计。
- 走执行网关 + OT 二次确认：必须产生 `write_operation` 审计与确认记录。
