# Implementation Plan（长期目标：L1→L4）

> 说明：本清单面向 GangQing 的**长期目标（L1→L4 + LLMOps + 数据基础设施）**，覆盖从“只读查询”到“受控闭环”的全链路能力；并非 MVP 任务清单。

## L1（最小闭环：只读查询 + SSE + 证据链 + 安全与审计）

- [ ] 1. 建立项目级对外契约基线：SSE 事件模型 + 统一错误模型 + Evidence schema（权威单一事实源）

  - 产物：完善 `docs/contracts/api-and-events-draft.md`（SSE 事件、错误码、Evidence 字段与约束）
  - 产物：补齐 `docs/api/openapi.yaml`（对话入口、错误响应、SSE 说明）
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：启动服务后跑 `backend/scripts/sse_smoke_test.py`
  - _Requirements: docs/requirements.md#R6.1, docs/requirements.md#R6.2, docs/requirements.md#R6.3, docs/requirements.md#R2.2, docs/design.md#3.5.1, docs/design.md#6.1_

- [ ] 2. 建立后端工程骨架（FastAPI 网关层 + RequestContext 贯穿 + 结构化日志）

  - 新增 `backend/` FastAPI 应用骨架与路由分层（API 网关 / 编排层 / 工具层）
  - 统一 `requestId` 生成与透传（HTTP→SSE→工具调用→审计）
  - 日志：JSON 结构化输出（至少 `requestId/sessionId/toolName/stepId`）
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`python -m compileall backend && python backend/scripts/start_server_and_healthcheck.py`
  - _Requirements: docs/design.md#2.3, docs/design.md#2.8, docs/design.md#6.1_

- [ ] 3. 建立认证与权限：JWT 登录 + RBAC 权限检查（API 与工具双层门禁）

  - 后端：实现登录、token 校验、中间件/依赖注入式 RBAC
  - 前端：接入登录态与 token 持久化（最小可用）
  - 权限失败：统一返回结构化错误（`FORBIDDEN`/`AUTH_ERROR`，英文 `message`）
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/auth_smoke_test.py`
  - _Requirements: docs/requirements.md#R1.1, docs/requirements.md#R1.2, docs/design.md#3.1_

- [ ] 4. 落地数据域隔离与脱敏策略（默认过滤 + 字段级脱敏 + 可审计）

  - 数据域过滤：在工具层强制叠加（多租户/产线/项目维度按配置）
  - 脱敏：按角色配置字段白名单与脱敏规则；证据链展示默认脱敏
  - 审计：记录命中策略与脱敏摘要（禁止敏感原文）
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/rbac_and_masking_smoke_test.py`
  - _Requirements: docs/requirements.md#R1.3, docs/requirements.md#R10.2, docs/design.md#4.4_

- [ ] 5. 设计并落地 Postgres 最小数据模型（维表/事实表/口径仓库/审计表）

  - 数据库：实现初始化迁移（表、索引、约束）
  - 表覆盖：设备/物料维表；产量/能耗/成本事实；报警事件；维修工单；指标口径仓库；审计日志
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/postgres_schema_smoke_test.py`
  - _Requirements: docs/requirements.md#R7.1, docs/design.md#2.6.1_

- [ ] 6. 实现可复现造数脚本（覆盖异常/边界，用于降级与 guardrail 验证）

  - 造数：同种子同数据；覆盖缺失值/延迟到达/重复/极端波动
  - 数据集：支持开发、冒烟测试、回归测试统一使用
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/seed_data_smoke_test.py`
  - _Requirements: docs/requirements.md#R7.2, docs/design.md#2.6.2_

- [ ] 7. 指标口径仓库：版本化口径 + 指标计算必须绑定 `lineage_version`

  - 定义指标实体（指标名、版本、公式、数据源、责任人）
  - 拒答策略：口径缺失/冲突时拒绝输出确定性结论
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/metric_lineage_smoke_test.py`
  - _Requirements: docs/requirements.md#R7.3, docs/design.md#5.2, docs/design.md#5.6_

- [ ] 8. 实现 Postgres 只读查询工具（模板化 SQL + 仅 SELECT + 证据对象输出）

  - 工具：仅允许 SELECT；字段白名单；行级过滤；超时控制
  - 输出：结构化结果 + Evidence（含 time_range/filters/extracted_at）
  - 审计：记录 tool.call/tool.result，参数脱敏
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/postgres_tool_smoke_test.py`
  - _Requirements: docs/requirements.md#R8.1, docs/design.md#2.5.2, docs/design.md#3.3_

- [ ] 9. 工具参数 schema 校验与契约校验（Pydantic 单一事实源）

  - 输入：工具参数使用 Pydantic 校验，无效返回 `VALIDATION_ERROR`
  - 输出：工具结果与模型输出进行 schema 校验，违规返回 `CONTRACT_VIOLATION`
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/contract_validation_smoke_test.py`
  - _Requirements: docs/requirements.md#R8.2, docs/requirements.md#R9.3, docs/design.md#6.1_

- [ ] 10. 工具超时与重试策略（可观测、可审计、可降级）

  - 超时：区分工具超时与模型超时，错误码映射 `UPSTREAM_TIMEOUT`
  - 重试：最多 3 次，记录次数与最终结果；流中输出 `warning/progress`
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/tool_timeout_retry_smoke_test.py`
  - _Requirements: docs/requirements.md#R8.3, docs/design.md#6.3, docs/design.md#6.4_

- [ ] 11. 接入 llama.cpp 推理服务（超时/错误码映射/健康检查联动）

  - 适配层：与 llama.cpp 通信；超时与错误映射 `UPSTREAM_UNAVAILABLE/UPSTREAM_TIMEOUT`
  - 健康检查：区分依赖不可用与系统 degraded
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/llamacpp_smoke_test.py`
  - _Requirements: docs/requirements.md#R9.1, docs/requirements.md#R12.3, docs/design.md#2.7.1_

- [ ] 12. 实现意图识别与策略路由（QUERY/ANALYZE/ALERT/ACTION_PREPARE/ACTION_EXECUTE）

  - 意图输出：类别 + 置信度；不明确必须澄清
  - 策略：写操作倾向/越权敏感查询必须拦截或进入只读默认
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/intent_routing_smoke_test.py`
  - _Requirements: docs/requirements.md#R15.1, docs/design.md#2.4, docs/design.md#3.9_

- [ ] 13. 编排层：工具链注册与 Function Calling（可控调用 + 可追溯证据）

  - 工具注册：配置化工具目录；可用工具集合由“角色 + 意图 + 数据域”约束
  - 事件：SSE 输出 `tool.call/tool.result`；错误时 `error` + `final`
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/tool_registry_smoke_test.py`
  - _Requirements: docs/requirements.md#R15.3, docs/design.md#2.5.3, docs/design.md#3.5.1_

- [ ] 14. 证据链引擎：Claim/Citation/Lineage/ToolCallTrace 组装与增量更新

  - 规则：数值回答必须绑定 citation+time_range；计算必须绑定 `lineage_version`
  - 流式：工具返回后持续输出 `evidence.update`
  - 降级：证据不足输出 `warning`，并在最终答复中明确不确定
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/evidence_smoke_test.py`
  - _Requirements: docs/requirements.md#R2.2, docs/requirements.md#R6.2, docs/design.md#3.3, docs/design.md#5.1_

- [ ] 15. SSE 服务端输出：进度/消息增量/证据增量/结构化错误/结束事件完整序列

  - 事件序列：`progress`→`tool.call`→`tool.result`→`message.delta`→`final`
  - 错误处理：发生错误必须尽快输出 `error`（含 `code/message/requestId/retryable`）并 `final`
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/sse_smoke_test.py`
  - _Requirements: docs/requirements.md#R6.1, docs/requirements.md#R6.3, docs/design.md#6.4_

- [ ] 16. 高风险意图/提示词注入防护：策略化拦截 + 审计留痕

  - 注入检测：直接/间接注入特征识别；输出安全校验
  - 拦截：越权/敏感查询 `FORBIDDEN`；写操作倾向 `GUARDRAIL_BLOCKED`
  - 证据链：记录规则 ID 与原因摘要（不含敏感细节）
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/security_guardrail_smoke_test.py`
  - _Requirements: docs/requirements.md#R10.1, docs/requirements.md#R10.3, docs/requirements.md#R17.2, docs/design.md#4.1_

- [ ] 17. 审计落库与不可篡改策略（append-only + 查询也要被审计）

  - 审计事件：query/tool_call/response/error/（L4 预留 approval/write_operation）
  - 权限：审计查询受控；写入 append-only
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/audit_log_smoke_test.py`
  - _Requirements: docs/requirements.md#R11.1, docs/requirements.md#R11.2, docs/design.md#2.8.1_

- [ ] 18. 健康检查与运行态自检（依赖状态/降级态/版本信息）

  - 健康检查：Postgres/llama.cpp/关键配置完整性
  - 返回：unhealthy/degraded 可区分，并可用于告警
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`python backend/scripts/start_server_and_healthcheck.py`
  - _Requirements: docs/requirements.md#R12.3, docs/design.md#2.9_

- [ ] 19. 前端三栏式布局 + SSE 流式渲染 + 证据链可视化（Context Panel/Trust Pill）

  - Web：三栏布局；对话区 message.delta 流式渲染
  - 证据面板：`evidence.update` 增量渲染；数值胶囊（Trust Pill）可展开证据
  - 断线：SSE 自动重连与提示
  - 验证（单元测试）：`npm -C web test`
  - 验证（冒烟测试）：`npm -C web run build && backend/scripts/web_sse_e2e_smoke_test.py`
  - _Requirements: docs/requirements.md#R13.1, docs/requirements.md#R13.2, docs/requirements.md#R13.3, docs/design.md#2.2_

## L2（诊断/多模态/可观测增强：RAG、并发、配额、移动端）

- [ ] 20. RAG 文档库与检索增强（手册/规程/故障库）：可追溯引用与间接注入防护

  - 文档摄取：分片、索引、版本管理；引用包含文档名+位置+片段ID
  - 规则：建议类结论必须附带引用；无证据必须声明 “no evidence found”
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/rag_smoke_test.py`
  - _Requirements: docs/requirements.md#R15.2, docs/design.md#3.8_

- [ ] 21. 模型并发控制与排队：队列满返回 `SERVICE_UNAVAILABLE`，并支持取消

  - 并发与队列：可配置；等待期间输出 `progress`
  - 取消：客户端取消向下传播（中断推理/工具调用）
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/concurrency_cancel_smoke_test.py`
  - _Requirements: docs/requirements.md#R9.2, docs/design.md#2.7.2_

- [ ] 22. Token 预算/配额与模型路由（SLM/LLM）：可审计的路由原因与降级策略

  - 路由：简单查询走小模型/模板化；复杂分析走大模型
  - 配额：超出返回 `FORBIDDEN` 或 `SERVICE_UNAVAILABLE`，并给出可执行降级建议
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/quota_routing_smoke_test.py`
  - _Requirements: docs/requirements.md#R15.4, docs/design.md#3.9_

- [ ] 23. 异常主动推送与告警升级（库存/设备报警/成本超标）：可订阅与可审计

  - 告警规则：阈值配置化；支持升级策略
  - 通道：SSE/站内通知（按设计落地）
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/alerting_smoke_test.py`
  - _Requirements: docs/requirements.md#R2.4, docs/design.md#2.4.1_

- [ ] 24. 智能交接班：班次摘要、异常与未闭环事项、关键操作追溯

  - 汇总：异常事件、未闭环报警、参数调整、遗留待办
  - 追溯：关键操作（谁/何时/为何）来自审计与事件模型
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/shift_handover_smoke_test.py`
  - _Requirements: docs/requirements.md#R2.5, docs/design.md#2.8.1_

- [ ] 25. 设备多模态诊断（图像/音频）+ 维修方案推荐 + 设备历史聚合

  - 多模态输入：隔离与脱敏；输出置信度与备选诊断
  - 维修方案：必须绑定来源（历史工单/手册条款/故障库）与证据链
  - 历史查询：统一实体 ID 映射后再跨系统聚合
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/maintenance_multimodal_smoke_test.py`
  - _Requirements: docs/requirements.md#R3.1, docs/requirements.md#R3.2, docs/requirements.md#R3.3, docs/design.md#3.7_

- [ ] 26. OpenTelemetry traces/metrics：端到端链路追踪与关键指标采集

  - Trace：http.request/intent.classify/tool.query/llm.generate/evidence.build
  - Metrics：请求量、错误率、P50/P95/P99、队列长度、工具延迟、推理延迟
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/otel_smoke_test.py`
  - _Requirements: docs/requirements.md#R12.1, docs/requirements.md#R12.2, docs/design.md#2.8.2_

- [ ] 27. 前端图表动态生成 + 移动端适配（弱网/离线/语音降级）

  - 图表：成本瀑布图、趋势折线、占比图表或表格
  - 移动端：语音输入与降级；弱网重连；离线缓存并标注 “offline data”
  - 验证（单元测试）：`npm -C web test`
  - 验证（冒烟测试）：`npm -C web run build && backend/scripts/mobile_weaknet_smoke_test.py`
  - _Requirements: docs/requirements.md#R13.4, docs/requirements.md#R13.5, docs/requirements.md#R18.1, docs/requirements.md#R18.2, docs/design.md#3.11_

- [ ] 28. 纠错反馈闭环：点赞/点踩、纠错提交、审核入库、纳入 Golden Dataset

  - 反馈：绑定 requestId + evidence 引用；无依据标注 unverified
  - 审核：通过后进入知识库/规则库，并触发回归集更新
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/feedback_loop_smoke_test.py`
  - _Requirements: docs/requirements.md#R15.5, docs/design.md#3.9_

- [ ] 29. Golden Dataset 回归与发布门禁：模型/Prompt/工具链变更触发全量评估

  - 评估：准确率/拒答率/升级人工比例；产出评估报告并记录版本证据
  - 门禁：核心指标下降超过阈值阻止发布，输出差异样本清单
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/golden_dataset_regression_smoke_test.py`
  - _Requirements: docs/requirements.md#R17.1, docs/design.md#3.10_

## L3（决策辅助与防护栏增强：规程合规检查、物理约束一致性、事件对齐深化）

- [ ] 30. 规程合规检查与红线拦截（强制）：命中返回 `GUARDRAIL_BLOCKED` 并附规程引用

  - 规则：违反红线立即拦截；接近红线输出 `warning`
  - 证据链：记录命中规则 ID 与规程引用（不含敏感细节）
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/sop_compliance_smoke_test.py`
  - _Requirements: docs/requirements.md#R4.2, docs/design.md#3.8_

- [ ] 31. 工艺参数优化建议（决策辅助）：基于历史相似批次与约束清单输出建议

  - 输出：参数范围、调整理由、历史案例引用；缺少数据明确不确定
  - 证据：建议类结论必须至少 1 条可追溯引用
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/process_optimization_smoke_test.py`
  - _Requirements: docs/requirements.md#R4.1, docs/design.md#3.8_

- [ ] 32. 物理边界/变化率一致性校验（关键数值防幻觉）：越界阻断或降级

  - 规则：温度/压力/能耗/产量等关键数值的合理区间与变化率版本化
  - 行为：越界返回 `GUARDRAIL_BLOCKED` 或降级为“仅展示数据与来源”
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/physical_guardrail_smoke_test.py`
  - _Requirements: docs/requirements.md#R17.3, docs/requirements.md#R14.4, docs/design.md#5.1.3_

- [ ] 33. 事件模型与时间对齐深化：更多链路使用锚点事件/窗口对齐，并可视化展示

  - 对齐：证据链展示对齐规则、锚点事件、时间窗口
  - 失败：返回 `EVIDENCE_MISSING` 或输出 `warning`
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/time_alignment_smoke_test.py`
  - _Requirements: docs/requirements.md#R16.2, docs/design.md#5.4_

- [ ] 34. 数据质量评估前置：缺失/漂移/异常/延迟评分，低质量拒绝确定性结论

  - 质量分：记录等级与计算时间；证据链展示质量摘要
  - 行为：低于阈值拒绝或降级；触发审计与告警
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/data_quality_smoke_test.py`
  - _Requirements: docs/requirements.md#R16.3, docs/design.md#5.5_

- [ ] 35. 知识图谱增强（可选）：设备-故障-现象-备件-事件多跳关联（每跳可追溯）

  - 多跳链路：每跳输出证据来源；缺证据则降级为“已知关联与来源”
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/knowledge_graph_smoke_test.py`
  - _Requirements: docs/requirements.md#R16.4, docs/design.md#14.1_

## L4（受控写操作：草案→审批/多签→受控执行→回滚→审计）

- [ ] 36. 只读默认门禁强化：识别写意图并强制进入草案/审批流程（禁止直接执行）

  - 行为：任何不明确或高风险请求按只读处理；写倾向必须提示审批
  - 证据：审计记录拦截规则 ID 与原因摘要
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/read_only_default_smoke_test.py`
  - _Requirements: docs/requirements.md#R5.1, docs/design.md#1.7, docs/design.md#3.6.1_

- [ ] 37. 写操作草案生成（ACTION_PREPARE）：约束清单、目标函数、影响评估与可编辑草案

  - 草案：可编辑；显示冲突与调整建议；支持甘特/时序对比（按 UI 能力）
  - 审计：记录草案生成参数摘要与版本
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/action_prepare_smoke_test.py`
  - _Requirements: docs/requirements.md#R5.2, docs/design.md#3.6.2_

- [ ] 38. 审批与多签（approval）：按变更类型路由审批人，拒绝必须有原因并可追溯

  - 路由：涉及工艺红线/安全连锁触发强制多签
  - 状态机：pending/approved/rejected/expired；记录审批动作审计
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/approval_multisig_smoke_test.py`
  - _Requirements: docs/requirements.md#R5.3, docs/design.md#3.6.3_

- [ ] 39. 受控执行与回滚：执行前创建回滚点，失败自动回滚或熔断

  - 执行：通过安全网关（受控工具）执行；幂等 key；执行结果结构化
  - 回滚：一键回滚到上一次确认版本；全链路审计
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/controlled_execute_and_rollback_smoke_test.py`
  - _Requirements: docs/requirements.md#R5.4, docs/design.md#3.6.4_

- [ ] 40. 写操作 Kill Switch 与熔断：一键禁用写入路径（可审计、可配置）

  - 开关：配置外部化；变更必须写入审计
  - 行为：触发时所有写相关请求返回结构化错误并提示原因
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/kill_switch_smoke_test.py`
  - _Requirements: docs/design.md#2.9, docs/requirements.md#R5.4_

- [ ] 41. 沙箱仿真与培训模式：明确沙箱标识、模拟执行与后果推演、培训案例沉淀

  - 沙箱：隔离真实生产；模拟工具链；输出风险提示与规程引用
  - 训练：可导出培训案例（受控权限）并可追溯
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/sandbox_training_smoke_test.py`
  - _Requirements: docs/requirements.md#R5.5, docs/design.md#3.6_

## 跨阶段（持续性任务：性能/可用性/配置外部化/契约测试）

- [ ] 42. 性能与可靠性体系：P95 目标、降级策略、压测与容量基线

  - 指标：简单查询 P95<2s、复杂分析 P95<30s；过载返回 `SERVICE_UNAVAILABLE`
  - 压测：产出基线报告（P50/P95/P99）并可审计
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/performance_baseline_smoke_test.py`
  - _Requirements: docs/requirements.md#R14.1, docs/requirements.md#R14.2, docs/design.md#2.8.2_

- [ ] 43. 配置外部化与配置校验：`.env.example` 完整列举 + 启动快速失败（英文错误）

  - 配置：URL/端口/超时/重试/路由策略/配额/开关全部外部化
  - 校验：启动时 schema 校验；缺失关键配置直接失败
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/config_validation_smoke_test.py`
  - _Requirements: docs/design.md#2.9, docs/requirements.md#R14.5_

- [ ] 44. 契约测试体系：前端 Zod + 后端 Pydantic + SSE 事件 schema 自动断言

  - 对象：REST 响应、SSE 事件、Evidence、错误模型
  - 门禁：契约不一致阻止合并/发布（按 CI 落地）
  - 验证（单元测试）：`pytest -q && npm -C web test`
  - 验证（冒烟测试）：`backend/scripts/contract_tests_smoke_test.py`
  - _Requirements: docs/design.md#7.4, docs/requirements.md#R9.3_

## 补齐（对齐 reports/tasks.md 的缺失项；保持现有分期结构不变）

- [ ] 45. （L1/L2）模型推理适配层（llama.cpp 网关/适配器）：超时、并发、配额、观测能力收敛为统一模块

  - 模块：统一 llama.cpp 适配器，对外提供一致的调用接口与错误映射
  - 能力：超时、并发/队列、配额/限流、观测字段（requestId 关联）
  - 输出：关键结构化输出 schema 校验，失败重试/降级
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/llamacpp_smoke_test.py && backend/scripts/concurrency_cancel_smoke_test.py && backend/scripts/quota_routing_smoke_test.py`
  - _Requirements: docs/requirements.md#R9.1, docs/requirements.md#R9.2, docs/requirements.md#R15.4, docs/design.md#2.7_

- [ ] 46. （L1）前端 SSE 客户端状态机：loading/error/cancel/retry/timeout 与取消向下传播

  - `web/`：SSE 连接管理、事件解析、断线重连、超时与重试、取消传播
  - UI：分段渲染 `message.delta`、阶段 `progress`、结构化 `error`
  - 验证（单元测试）：`npm -C web test`
  - 验证（冒烟测试）：`npm -C web run build && backend/scripts/web_sse_e2e_smoke_test.py`
  - _Requirements: docs/requirements.md#R13.2, docs/requirements.md#R6.3, docs/design.md#3.5_

- [ ] 47. （L1）前端 Context Panel 强化：“证据缺失/不可验证/降级态”表达与可追溯展开

  - `web/components/ContextPanel.tsx`：展示 Evidence；支持缺失/冲突/降级态 UI
  - 行为：当后端输出 `warning` 或 evidence 不完整时，前端明确表达并引导用户补充信息
  - 验证（单元测试）：`npm -C web test`
  - 验证（冒烟测试）：`npm -C web run build && backend/scripts/web_sse_e2e_smoke_test.py`
  - _Requirements: docs/requirements.md#R6.2, docs/requirements.md#R14.4, docs/requirements.md#R13.3, docs/design.md#5.1_

- [ ] 48. （L2）管理驾驶舱/自然语言 BI：成本卡片、瀑布图/趋势图、结构化渲染与 lineage_version 绑定

  - 前端：成本构成瀑布图、对比趋势图组件；回答卡片结构化渲染
  - 后端：分析型查询模板与聚合口径（强制引用 `lineage_version`）
  - 验证（单元测试）：`pytest -q && npm -C web test`
  - 验证（冒烟测试）：`backend/scripts/bi_query_smoke_test.py && npm -C web run build`
  - _Requirements: docs/requirements.md#R2.3, docs/requirements.md#R13.4, docs/design.md#3.4_

- [ ] 49. （L2）多模态上传管线：图片/音频上传（安全隔离、大小限制、脱敏、审计）

  - 后端：多模态上传接口（权限、大小/格式限制、隔离存储、审计）
  - 编排层：多模态解析→检索→结论与不确定项（证据链化）
  - 前端：上传/录音交互与结果可追溯展示
  - 验证（单元测试）：`pytest -q && npm -C web test`
  - 验证（冒烟测试）：`backend/scripts/multimodal_smoke_test.py`
  - _Requirements: docs/requirements.md#R3.1, docs/design.md#3.7_

- [ ] 50. （L2）设备诊疗专家外部系统接入：EAM 工单/备件/BOM 只读连接器与证据链输出

  - 工具层：EAM 连接器（只读查询优先）；字段脱敏与 RBAC
  - Evidence：工单详情、用件清单、时间范围与数据源
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/eam_connector_smoke_test.py`
  - _Requirements: docs/requirements.md#R3.2, docs/requirements.md#R3.3, docs/design.md#2.5.3_

- [ ] 51. （L2）Token 预算与配额增强：缓存与高频问题模板化（成本治理）

  - 后端：按用户/角色/场景配额；缓存策略；高频查询走模板与小模型
  - 观测：配额命中率、缓存命中率，绑定 `requestId`
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/quota_and_cache_smoke_test.py`
  - _Requirements: docs/requirements.md#R15.4, docs/design.md#2.7.2_

- [ ] 52. （L2）GUI/LUI 融合：圈选提问（图表/报表圈选）与证据定位高亮

  - 前端：图表交互选择与上下文提交；证据定位高亮
  - 后端：接收圈选上下文并绑定 evidence
  - 验证（单元测试）：`npm -C web test && pytest -q`
  - 验证（冒烟测试）：`npm -C web run build && backend/scripts/web_sse_e2e_smoke_test.py`
  - _Requirements: docs/requirements.md#R13.4, docs/design.md#2.2_

- [ ] 53. （L2+）工具链扩展：ERP/MES/DCS/LIMS 连接器规范化接入（统一参数校验、超时重试、脱敏、审计、Evidence）

  - 工具层：按连接器类型实现适配模板与能力矩阵
  - 观测：每个连接器的耗时、失败率与重试统计
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/connectors_integration_smoke_test.py`
  - _Requirements: docs/requirements.md#R15.3, docs/design.md#2.5.3_

- [ ] 54. （L3+）数据基础设施演进：工业时序数据接入与冷热分层（支撑事件对齐与分析链路）

  - 数据：时序数据存储与查询策略；对齐事件模型
  - 治理：数据血缘、口径版本与权限域
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/timeseries_smoke_test.py`
  - _Requirements: docs/requirements.md#R16.2, docs/design.md#2.6_

- [ ] 55. （跨阶段）生产级发布与回归门禁：CI 触发（契约/单元/冒烟/Golden Dataset）+ 版本化发布 + 回滚策略

  - CI：合并前强制跑单元 + 冒烟 + 契约校验 + Golden Dataset 回归
  - 版本：文档/契约/指标口径/数据集 版本一致性校验
  - 回滚：发布失败可回滚到上一个可用版本，并保留审计证据
  - 验证（单元测试）：`pytest -q && npm -C web test`
  - 验证（冒烟测试）：`backend/scripts/full_pipeline_smoke_test.py && npm -C web run build`
  - _Requirements: docs/requirements.md#R17.1, docs/design.md#7, docs/design.md#8_

- [ ] 56. （L1+）统一语义层（实体与 ID 映射）：设备/物料/批次/订单统一 ID 映射与冲突治理

  - 数据层：映射表、冲突检测、版本化；映射变更可追溯
  - 工具层：跨系统聚合必须基于统一 ID；映射缺失/冲突返回 `EVIDENCE_MISMATCH`
  - Evidence：引用统一 ID 与映射版本信息（摘要）
  - 验证（单元测试）：`pytest -q`
  - 验证（冒烟测试）：`backend/scripts/semantic_id_mapping_smoke_test.py`
  - _Requirements: docs/requirements.md#R16.1, docs/design.md#5.3_
