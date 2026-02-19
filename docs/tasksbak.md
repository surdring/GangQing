# Implementation Plan

> 说明：本清单面向 GangQing 的**长期目标（L1→L4 + LLMOps + 数据基础设施）**，覆盖从“只读查询”到“受控闭环”的全链路能力；并非 MVP 任务清单。

- [ ] 1. 建立项目级对外契约基线：SSE 事件模型 + 统一错误模型 + Evidence schema（权威单一事实源）

  - 产物：补齐 `docs/contracts/api-and-events-draft.md`（SSE 事件、错误码、Evidence 字段与约束）
  - 产物：补齐 `docs/api/openapi.yaml` 中对话入口与错误响应声明
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：启动服务后跑 `backend/scripts/sse_smoke_test.py`
  - _Requirements: docs/技术设计文档-最佳实践版.md#4, docs/技术设计文档-最佳实践版.md#4.2, docs/技术设计文档-最佳实践版.md#4.3, docs/技术设计文档-最佳实践版.md#4.3, docs/技术设计文档-最佳实践版.md#5, docs/产品需求.md#F1.3_

- [ ] 2. 建立后端工程骨架（FastAPI 网关层 + RequestContext 贯穿 + 结构化日志）

  - 新增 `backend/` FastAPI 应用与路由分层（API 网关 / 编排层 / 工具层）
  - 统一 `requestId` 生成与透传（HTTP→SSE→工具调用→审计）
  - 日志：JSON 结构化输出（至少 `requestId/sessionId/toolName/stepId`）
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`python -m compileall backend && python backend/scripts/start_server_and_healthcheck.py`
  - _Requirements: docs/技术设计文档-最佳实践版.md#2.1, docs/技术设计文档-最佳实践版.md#2.2, docs/技术设计文档-最佳实践版.md#11_

- [ ] 3. 建立模型推理适配层（llama.cpp 网关/适配器：超时、并发、配额、观测）

  - 新增“模型适配器”模块：与 llama.cpp 通信、超时、并发队列、错误码映射
  - 输出约束：对关键结构化输出（意图/计划/证据链）做 schema 校验，失败重试/降级
  - 观测：记录 tokens/latency（若可用）与 `requestId` 关联
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/llamacpp_smoke_test.py`
  - _Requirements: docs/技术设计文档-最佳实践版.md#9, docs/技术设计文档-最佳实践版.md#3.4_

- [ ] 4. 实现意图识别与策略路由（QUERY/ANALYZE/ALERT/ACTION_PREPARE/ACTION_EXECUTE）

  - 编排层新增意图分类与路由规则；默认只读；高风险意图进入拦截/HITL 预留
  - 统一在 SSE 中输出 `progress`（意图识别阶段）与 `warning`（降级/不确定项）
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/intent_routing_smoke_test.py`
  - _Requirements: docs/技术设计文档-最佳实践版.md#6, docs/产品需求.md#3_

- [ ] 5. 建设 Postgres 数据层（最小数据模型 + 可复现造数 + 异常/边界覆盖）

  - 建表：设备/物料维表、产量/能耗/成本事实表、报警事件、维修工单、指标口径、审计日志
  - 造数脚本：固定种子、可复现；包含缺失/延迟/极端波动用于降级与 guardrail 验证
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/postgres_seed_and_query_smoke_test.py`
  - _Requirements: docs/技术设计文档-最佳实践版.md#8, docs/技术设计文档-最佳实践版.md#8.3, docs/产品需求.md#40-47_

- [ ] 6. 实现 L1 只读查询工具（Postgres）：模板化查询 + 字段白名单 + 参数校验 + 脱敏 + 审计

  - 工具层：仅允许 `SELECT`；禁止模型自由拼接 SQL；按角色限制字段/数据域
  - 返回：工具结果摘要 + Evidence Citation + Tool Call Trace
  - 审计：记录 query、tool_call、result/error、dataScope
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/postgres_tool_smoke_test.py`
  - _Requirements: docs/技术设计文档-最佳实践版.md#7, docs/技术设计文档-最佳实践版.md#7.2, docs/技术设计文档-最佳实践版.md#11, docs/产品需求.md#F1.1_

- [ ] 7. 建立 Evidence 证据链引擎（Claims/Citations/Lineage/ToolCalls/Uncertainty）与“数值不可幻觉”门禁

  - 规则：任何数值必须绑定 citation（含时间范围）与 lineage_version；不满足则降级并输出 `warning`
  - 前端可追问：数据源/时间范围/口径版本/过滤条件（脱敏）
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/evidence_smoke_test.py`
  - _Requirements: docs/技术设计文档-最佳实践版.md#5, docs/技术设计文档-最佳实践版.md#5.3, docs/产品需求.md#F1.3_

- [ ] 8. 建设指标口径仓库（Metric Lineage）：版本化、责任人、变更记录、definition_uri

  - 数据层与 API：支持查询指标定义、版本、公式 ID、变更记录
  - 编排层：回答中强制引用 lineage_version
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/metric_lineage_smoke_test.py`
  - _Requirements: docs/产品需求.md#43-47, docs/产品需求.md#121, docs/技术设计文档-最佳实践版.md#5.2_

- [ ] 9. 建立审计日志（不可抵赖方向）：查询/工具调用/响应摘要/错误 的全覆盖落库与检索

  - 后端：审计表与写入管线；参数摘要脱敏；关联 `requestId/sessionId/userId/role`
  - 提供审计查询 API（按 RBAC 限制）
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/audit_log_smoke_test.py`
  - _Requirements: docs/技术设计文档-最佳实践版.md#11, docs/产品需求.md#100, docs/产品需求.md#F1.4_

- [ ] 10. 安全基座：RBAC（角色→工具→数据域→字段）+ 字段级脱敏策略 + 输出过滤

  - 后端：RBAC 中间件与权限模型；工具调用白名单；字段脱敏策略（按角色）
  - 防注入：输入分区、工具参数校验、输出过滤（敏感信息/系统指令泄露特征）
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/rbac_and_masking_smoke_test.py`
  - _Requirements: docs/技术设计文档-最佳实践版.md#3.1, docs/技术设计文档-最佳实践版.md#10, docs/产品需求.md#97-104_

- [ ] 11. 可观测性：OpenTelemetry traces/metrics（建议项落地为生产级基线）

  - Span：`http.request/intent.classify/tool.postgres.query/llm.generate/evidence.build`
  - 指标：请求量、错误率、P95/P99、工具失败率、模型队列长度
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/otel_smoke_test.py`
  - _Requirements: docs/技术设计文档-最佳实践版.md#12_

- [ ] 12. 前端对话与 SSE 客户端状态机（loading/error/cancel/retry/timeout）

  - `web/`：实现 SSE 连接管理、事件解析、断线重连、取消传播
  - UI：分段渲染 `message.delta`、阶段 `progress`、结构化 `error`
  - 验证（单元测试）：`npm test`
  - 验证（冒烟测试）：`npm run build && node web/scripts/sse_e2e_smoke_test.mjs`
  - _Requirements: docs/技术设计文档-最佳实践版.md#2.1, docs/技术设计文档-最佳实践版.md#4.2, docs/产品需求.md#112-114_

- [ ] 13. 前端 Context Panel：Evidence 可视化（Claims→Citations→Lineage→ToolCalls）与“证据缺失/降级态”表达

  - `web/components/ContextPanel.tsx`：展示证据链、引用胶囊、时间范围、口径版本
  - UI：支持“证据缺失/不可验证”状态与提示
  - 验证（单元测试）：`npm test`
  - 验证（冒烟测试）：`npm run build && node web/scripts/context_panel_smoke_test.mjs`
  - _Requirements: docs/技术设计文档-最佳实践版.md#5, docs/产品需求.md#F1.3, docs/产品需求.md#9.2.1_

- [ ] 14. 管理驾驶舱：自然语言 BI 输出卡片（瀑布图/趋势图）与指标对比能力（F1.1）

  - 前端：成本构成瀑布图、对比趋势图组件；回答卡片结构化渲染
  - 后端：分析型查询模板与聚合口径（引用 lineage_version）
  - 验证（单元测试）：`pytest -q && npm test`
  - 验证（冒烟测试）：`backend/scripts/bi_query_smoke_test.py && node web/scripts/bi_ui_smoke_test.mjs`
  - _Requirements: docs/产品需求.md#F1.1, docs/产品需求.md#195-205_

- [ ] 15. 智能交接班（F1.4）：异常事件/未闭环报警/参数变更审计/遗留待办 的自动汇总

  - 后端：交接班聚合器（事件 + 审计 + 工单 + 待办）并输出 evidence
  - 前端：交接班聚合页与可追溯展开
  - 验证（单元测试）：`pytest -q && npm test`
  - 验证（冒烟测试）：`backend/scripts/shift_handover_smoke_test.py && node web/scripts/shift_handover_smoke_test.mjs`
  - _Requirements: docs/产品需求.md#F1.4, docs/技术设计文档-最佳实践版.md#2.2_

- [ ] 16. 异常主动推送（F1.2 / ALERT 意图）：阈值/规则引擎 + 通知通道 + 审计

  - 后端：预警规则（库存阈值、订单压力、设备报警）与推送管线（Web 通知/SSE）
  - 前端：通知中心与可一键打开证据链
  - 验证（单元测试）：`pytest -q && npm test`
  - 验证（冒烟测试）：`backend/scripts/alert_push_smoke_test.py && node web/scripts/alert_ui_smoke_test.mjs`
  - _Requirements: docs/产品需求.md#F1.2, docs/技术设计文档-最佳实践版.md#6_

- [ ] 17. L2 文档库 + RAG：设备手册/故障库/工艺规范 的检索增强（含间接注入防护）

  - 数据层：文档入库、版本化、权限域、向量索引
  - 编排层：检索→引用→回答；输出 citations（文档来源与段落定位）
  - 安全：外部内容隔离、恶意指令过滤
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/rag_smoke_test.py`
  - _Requirements: docs/产品需求.md#3, docs/产品需求.md#F2.1, docs/技术设计文档-最佳实践版.md#10.1_

- [ ] 18. L2 多模态输入：图片/音频上传管线（安全隔离、大小限制、脱敏、审计）

  - 后端：多模态上传接口（权限、大小/格式限制、隔离存储、审计）
  - 编排层：多模态解析→检索→结论与不确定项
  - 前端：上传/录音交互与结果可追溯展示
  - 验证（单元测试）：`pytest -q && npm test`
  - 验证（冒烟测试）：`backend/scripts/multimodal_smoke_test.py && node web/scripts/multimodal_ui_smoke_test.mjs`
  - _Requirements: docs/产品需求.md#F2.1, docs/技术设计文档-最佳实践版.md#14.2_

- [ ] 19. 设备诊疗专家（F2.2）：EAM 工单/备件/BOM 查询适配器与证据链输出

  - 工具层：EAM 连接器（只读查询优先）；字段脱敏与 RBAC
  - 证据链：工单详情、用件清单、时间范围与数据源
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/eam_connector_smoke_test.py`
  - _Requirements: docs/产品需求.md#F2.2, docs/技术设计文档-最佳实践版.md#2.1_

- [ ] 20. L3 事件模型与时序对齐：生产事件（开炉/停机/报警等）与 OT 时序数据锚点对齐策略

  - 数据层：事件表与对齐规则（窗口/锚点）；对齐结果写入 evidence
  - 编排层：分析时必须显式声明对齐规则与时间窗口
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/event_alignment_smoke_test.py`
  - _Requirements: docs/产品需求.md#45-46, docs/产品需求.md#122, docs/技术设计文档-最佳实践版.md#14.3_

- [ ] 21. L3 物理边界与变化率 guardrail：关键参数一致性校验与降级

  - 后端：物理区间/变化率规则库；触发时输出 `warning` 并记录审计
  - 前端：明确展示“已降级为仅展示数据与来源/需人工复核”
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/guardrail_smoke_test.py`
  - _Requirements: docs/产品需求.md#39, docs/技术设计文档-最佳实践版.md#3.2_

- [ ] 22. 生产工艺智库：参数设定辅助（F3.1）——相似批次检索 + Best Practice 复用 + 不确定项管理

  - 工具层：相似批次检索（事件/物料/设备/窗口）
  - 编排层：建议必须列出约束清单与证据链；缺数据则拒答/降级
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/process_advice_smoke_test.py`
  - _Requirements: docs/产品需求.md#F3.1, docs/技术设计文档-最佳实践版.md#3.2_

- [ ] 23. 规程合规检查（F3.2）：指令/建议的红线校验与越界拦截（输出可追溯条款引用）

  - 规则库：工艺红线与规程条款（可版本化）
  - 输出：拦截原因、条款引用、风险说明（证据链化）
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/compliance_check_smoke_test.py`
  - _Requirements: docs/产品需求.md#F3.2, docs/产品需求.md#119-120_

- [ ] 24. 统一语义层（实体与 ID 映射）：设备/点位/物料/炉次/订单 的全域映射与冲突治理

  - 数据层：映射表、冲突检测、版本化
  - 工具层：查询统一 ID 并回填到 evidence
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/semantic_id_mapping_smoke_test.py`
  - _Requirements: docs/产品需求.md#43-46_

- [ ] 25. 知识图谱（可选增强）：设备-故障-现象-备件-工艺-事件 的关系抽取与多跳检索

  - 数据层：图谱存储与增量更新；权限域隔离
  - 编排层：多跳推理必须附带可追溯路径与引用
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/kg_smoke_test.py`
  - _Requirements: docs/产品需求.md#47_

- [ ] 26. Token 预算与配额：SLM/LLM 路由、缓存与高频问题模板化（成本治理）

  - 后端：按用户/角色/场景配额；缓存策略；高频查询走模板与小模型
  - 观测：配额命中率、缓存命中率
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/quota_and_cache_smoke_test.py`
  - _Requirements: docs/产品需求.md#123, docs/技术设计文档-最佳实践版.md#9.2_

- [ ] 27. 反馈闭环（RLHF for Industry）：点赞/点踩/纠错 → 待审核队列 → 知识库/规则库/Golden Dataset 回归

  - 前端：纠错入口与表单；提交后可追踪
  - 后端：反馈入库、审核流（最小流程）、回归集更新记录
  - 验证（单元测试）：`pytest -q && npm test`
  - 验证（冒烟测试）：`backend/scripts/feedback_loop_smoke_test.py && node web/scripts/feedback_ui_smoke_test.mjs`
  - _Requirements: docs/产品需求.md#152-155_

- [ ] 28. Golden Dataset 与自动化评估：覆盖术语/故障/SOP/指标口径/红线拦截 的回归体系

  - 数据：构建金标准集与版本管理；变更触发全量回归
  - 评估：准确率/拒答率/升级人工比例等指标计算与报表
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/eval_golden_dataset_smoke_test.py`
  - _Requirements: docs/产品需求.md#37-39, docs/技术设计文档-最佳实践版.md#13_

- [ ] 29. 数据质量评估前置（Data Sanitation）：缺失/漂移/异常/造假风险/口径一致性 的检测与分级

  - 后端：数据质量规则与评分；Evidence 中展示质量等级
  - 运营：质量看板与告警
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/data_quality_smoke_test.py`
  - _Requirements: docs/产品需求.md#155-158_

- [ ] 30. 移动端能力补齐：弱网/离线缓存（手册/SOP/常见故障流程）与网络恢复自动同步

  - 前端：离线包管理、缓存策略、同步状态机
  - 后端：离线包分发与版本控制、权限校验
  - 验证（单元测试）：`npm test && pytest -q`
  - 验证（冒烟测试）：`node web/scripts/offline_mode_smoke_test.mjs && backend/scripts/offline_package_smoke_test.py`
  - _Requirements: docs/产品需求.md#111-112, docs/产品需求.md#250-261_

- [ ] 31. 抗噪与语音交互策略：语音优先 + 降噪策略 + 自动降级为文字交互

  - 前端：语音采集、识别、噪声环境探测与降级
  - 后端：语音转写接口适配与审计
  - 验证（单元测试）：`npm test && pytest -q`
  - 验证（冒烟测试）：`node web/scripts/voice_smoke_test.mjs && backend/scripts/asr_smoke_test.py`
  - _Requirements: docs/产品需求.md#105-110, docs/产品需求.md#230-249_

- [ ] 32. GUI/LUI 融合：圈选提问（图表/报表圈选）与屏显指引（从证据定位到 UI 高亮）

  - 前端：图表交互选择与上下文提交；证据定位高亮
  - 后端：接收圈选上下文并绑定 evidence
  - 验证（单元测试）：`npm test && pytest -q`
  - 验证（冒烟测试）：`node web/scripts/selection_query_smoke_test.mjs`
  - _Requirements: docs/产品需求.md#112-114_

- [ ] 33. L4 策略基座：Read-Only Default 的制度化落地 + 写操作意图的强拦截与 HITL 预留

  - 后端：写操作能力必须走 `ACTION_PREPARE`；`ACTION_EXECUTE` 默认禁用
  - 审计：任何写意图都必须落审计并可追溯
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/read_only_default_smoke_test.py`
  - _Requirements: docs/技术设计文档-最佳实践版.md#2.3, docs/技术设计文档-最佳实践版.md#6.2, docs/产品需求.md#F4.1_

- [ ] 34. 写操作草案（F4.2）：排产/工单/领料/采购 的草案生成（可编辑、可解释、可审计）

  - 后端：草案对象模型与存储；草案必须包含约束、目标函数、影响评估与 evidence
  - 前端：草案编辑器与差异对比（如甘特图对比）
  - 验证（单元测试）：`pytest -q && npm test`
  - 验证（冒烟测试）：`backend/scripts/action_prepare_smoke_test.py && node web/scripts/draft_ui_smoke_test.mjs`
  - _Requirements: docs/产品需求.md#F4.2, docs/技术设计文档-最佳实践版.md#2.3_

- [ ] 35. 审批与多签（F4.3）：审批链配置、权限与职责分离、审批审计

  - 后端：审批流程引擎（最小可用：提交/同意/拒绝/追问）；多角色多签
  - 前端：审批面板与审批链可视化
  - 验证（单元测试）：`pytest -q && npm test`
  - 验证（冒烟测试）：`backend/scripts/approval_flow_smoke_test.py && node web/scripts/approval_ui_smoke_test.mjs`
  - _Requirements: docs/产品需求.md#F4.3, docs/技术设计文档-最佳实践版.md#2.3_

- [ ] 36. 受控执行与回滚（F4.4）：安全网关、幂等键、执行状态机、回滚点记录、熔断

  - 后端：执行引擎（持久化、可恢复、幂等、重试边界）
  - 安全：安全网关与 kill switch；执行过程全审计
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/action_execute_and_rollback_smoke_test.py`
  - _Requirements: docs/产品需求.md#F4.4, docs/技术设计文档-最佳实践版.md#2.3_

- [ ] 37. 沙箱仿真与培训模式（F4.5）：历史回放、参数滑块推演、风险提示与条款引用

  - 后端：仿真模式开关（强隔离，禁止真实写入）；回放数据集与推演输出 evidence
  - 前端：SIMULATION MODE UI、推演结果与风险可视化
  - 验证（单元测试）：`pytest -q && npm test`
  - 验证（冒烟测试）：`backend/scripts/simulation_mode_smoke_test.py && node web/scripts/simulation_ui_smoke_test.mjs`
  - _Requirements: docs/产品需求.md#F4.5, docs/产品需求.md#272-276_

- [ ] 38. 工具链扩展：ERP/MES/DCS/LIMS 连接器规范化接入（统一参数校验、超时重试、脱敏、审计、Evidence）

  - 工具层：按连接器类型实现适配模板与能力矩阵
  - 观测：每个连接器的耗时、失败率与重试统计
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/connectors_integration_smoke_test.py`
  - _Requirements: docs/产品需求.md#34-35, docs/技术设计文档-最佳实践版.md#7.1_

- [ ] 39. 数据基础设施演进：工业数据湖/时序数据接入与冷热分层（为 L3/L4 提供支撑）

  - 数据：时序数据存储与查询策略；对齐事件模型
  - 治理：数据血缘、口径版本与权限域
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/timeseries_smoke_test.py`
  - _Requirements: docs/产品需求.md#40-46_

- [ ] 40. 生产级发布与回归门禁：CI 触发（契约/单元/冒烟/Golden Dataset）+ 版本化发布 + 回滚策略

  - CI：合并前强制跑单元 + 冒烟 + 契约校验 + Golden Dataset 回归
  - 版本：文档/契约/指标口径/数据集 版本一致性校验
  - 验证（单元测试）：`pytest -q && npm test`
  - 验证（冒烟测试）：`backend/scripts/full_pipeline_smoke_test.py && node web/scripts/full_pipeline_ui_smoke_test.mjs`
  - _Requirements: docs/产品需求.md#37-39, docs/技术设计文档-最佳实践版.md#13, docs/技术设计文档-最佳实践版.md#14_
