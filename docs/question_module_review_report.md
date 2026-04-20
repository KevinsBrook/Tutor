# 出题模块今晚改动技术报告（全量变更版）

## 1. 报告说明
- 报告目标：汇总今晚围绕“出题模块 + 作业评审链路”完成的全部实现，不再仅列错误。
- 统计口径：以当前工作区变更为准（含新增文件与修改文件）。
- 对应阶段：覆盖 Phase 0 ~ Phase 6 中已落地部分。

## 2. 今晚完成的核心结果
1. 出题页从原先单一页面重构为统一工作台，打通教师发布、学生提交、教师评审、错题沉淀、再练生成。
2. 题目能力从 `choice/written` 扩展到多题型统一 schema，并支持 Bloom 认知层级。
3. 新增作业评审后端（assignment-review）与 JSON 仓储层，形成可持续演进的存储结构。
4. 新增登录鉴权壳（演示账号）与角色化入口（教师/学生）。
5. 增强导出、审核面板、计时考试模式、错题本再练策略等产品化能力。

## 3. 分阶段实现明细

### Phase 0：数据契约与最小架构
#### 3.1 统一 schema 与契约扩展
- 文件：`web/types/question.ts`
- 主要改动：
  - 扩展题型枚举：`choice`、`multiple_choice`、`true_false`、`fill_blank`、`matching`、`term_definition`、`ordering`、`written`、`mixed`。
  - 扩展题目结构字段：`blanks`、`pairs`、`steps`、`source_refs`、`distractor_meta`。
  - 扩展审核字段：`audit` 中新增溯源计数、干扰项候选/入选/去重等指标。

#### 3.2 仓储抽象（JSON 兼容）
- 文件：`src/agents/question/repository.py`
- 主要改动：
  - 新增 `QuestionRunRepository` 协议。
  - 新增 `JsonQuestionRunRepository` 实现，统一保存 `knowledge/plan/result/summary`。

- 文件：`src/api/utils/assignment_review_repository.py`
- 主要改动：
  - 新增 `AssignmentReviewRepository` 协议。
  - 新增 `JsonAssignmentReviewRepository`，抽离 JSON 读写与初始化。

- 文件：`src/api/utils/assignment_review_store.py`
- 主要改动：
  - 新增 `AssignmentReviewStore`，统一管理 `assignments/submissions/wrongbook` 三类数据。
  - 形成线程锁保护、统一路径组织、统一 CRUD 接口。

### Phase 1：前端壳改造（登录与角色入口）
#### 3.3 登录、鉴权与页面壳
- 文件：`web/context/AuthContext.tsx`
- 主要改动：
  - 新增本地登录上下文。
  - 演示账号：`teacher/teacher123`、`student/student123`。

- 文件：`web/app/login/page.tsx`
- 主要改动：
  - 新增中文登录页，教师/学生双入口提示。

- 文件：`web/components/AppShell.tsx`
- 主要改动：
  - 新增路由守卫：未登录跳转 `/login`，已登录访问 `/login` 回跳 `/question`。

- 文件：`web/app/layout.tsx`
- 主要改动：
  - 接入 `AuthProvider` 与 `AppShell`。

#### 3.4 导航与中文化改造
- 文件：`web/components/Sidebar.tsx`
- 主要改动：
  - 删除顶部品牌与外链按钮占位（满足“精简顶部空间”诉求）。
  - 增加角色信息与退出登录。
  - 学生角色动态展示“错题本”入口。

- 文件：`web/app/question/page.tsx`
- 主要改动：
  - 页面入口重定向到统一工作台 `AssignmentReviewWorkspace`。

### Phase 2：教师侧任务发布与评审入口
#### 3.5 作业发布 API 与发布确认机制
- 文件：`src/api/routers/assignment_review.py`
- 主要改动：
  - 新增教师端 API：
    - `POST /teacher/rubric-draft`：从标题/描述/文件名生成任务要点与 rubric 草稿。
    - `POST /teacher/assignments`：创建作业并上传附件。
    - `POST /teacher/assignments/{id}/confirm`：教师确认发布（学生可见前置条件）。
    - `GET /teacher/assignments`、`GET /teacher/submissions`。
  - 上传文件格式支持：`.pdf/.doc/.docx/.txt/.md/.rtf/.html/.htm`。

#### 3.6 教师评审前端工作区
- 文件：`web/app/question/AssignmentReviewWorkspace.tsx`
- 主要改动：
  - 新增教师发布表单（作业标题、说明、rubric 编辑、附件上传）。
  - 新增“生成 rubric 草稿”交互。
  - 新增“确认发布”动作。
  - 新增教师评审区：总分、评语、rubric 分维评分、结构化错题项录入。

### Phase 3：学生提交与结构化批改
#### 3.7 学生提交链路与自动评审
- 文件：`src/api/routers/assignment_review.py`
- 主要改动：
  - 新增学生端 API：
    - `GET /student/published`：仅获取已确认发布作业。
    - `POST /student/submissions`：提交答案与文件。
    - 自动生成 `auto_review`：相关性、总分、分维得分、错误项、缺失点、建议、摘要。
    - `GET /student/submissions`：查看个人提交记录。

#### 3.8 主观题评分接口（题目练习链路）
- 文件：`src/api/routers/question.py`
- 主要改动：
  - 新增 `POST /evaluate/written`。
  - 评分机制：LLM 优先，失败回退规则评分。
  - 输出结构：`status`、`score_ratio`、`reason`、`source`（llm/rule）。

### Phase 4：错题本与再练策略
#### 3.9 错题本沉淀与再练 API
- 文件：`src/api/routers/assignment_review.py`
- 主要改动：
  - 新增错题本 API：
    - `GET /student/wrongbook`
    - `POST /student/wrongbook/{item_id}/practice`
    - `POST /student/wrongbook/custom`
  - 再练策略：`same_point`、`harder`、`easier`、`variant`。

- 文件：`src/api/utils/assignment_review_store.py`
- 主要改动：
  - 评审完成后自动沉淀错题项。
  - 支持 `practice_history` 持久化。

#### 3.10 错题本页面
- 文件：`web/app/wrongbook/page.tsx`
- 主要改动：
  - 新增中文错题本页面。
  - 新增四类再练按钮并展示最近再练记录。

### Phase 5：增强能力包（九方向）已落地项
#### 3.11 题型扩展与统一生成后处理
- 文件：`src/agents/question/agents/generate_agent.py`
- 主要改动：
  - 基于 `requested_type` 的 schema 提示增强。
  - 新增多题型解析与规范化：多选、判断、填空、匹配、术语定义、排序。
  - 新增题型专属字段补全逻辑（`blanks/pairs/steps`）。

- 文件：`src/agents/question/quality.py`
- 主要改动：
  - 新增 `normalize_question_type`、`normalize_bloom_level`、`normalize_question_schema`、`build_question_audit`。
  - 输出质量审计指标：相关性、难度匹配、答案唯一性、干扰项质量、超纲风险、含糊性、LaTeX、溯源与干扰项统计。

#### 3.12 Bloom 层级控制
- 文件：`web/app/question/AssignmentReviewWorkspace.tsx`
- 主要改动：
  - 前端配置新增 Bloom 六层：记忆/理解/应用/分析/评价/创造。
  - 透传到出题请求并在题卡展示。

#### 3.13 干扰项质量增强（两阶段）
- 文件：`src/agents/question/agents/generate_agent.py`
- 主要改动：
  - `choice`、`multiple_choice` 新增“候选清洗 + 排序筛选”流程。
  - 产出 `distractor_meta`（candidate/selected/duplicate_removed）。

#### 3.14 导出能力增强
- 文件：`web/app/question/AssignmentReviewWorkspace.tsx`
- 主要改动：
  - 题目导出：JSON、Markdown、CSV、GIFT、AIKEN、Moodle XML。
  - 评审记录导出：单条与批量（JSON/Markdown/CSV）。
  - 练习成绩导出：JSON/CSV。

#### 3.15 计时考试模式与成绩单
- 文件：`web/app/question/AssignmentReviewWorkspace.tsx`
- 主要改动：
  - 新增练习模式/考试模式切换。
  - 考试模式倒计时与自动交卷。
  - 生成结构化成绩单（每题判定、得分、原因、总分）。

#### 3.16 题目溯源与审核面板增强
- 文件：`src/agents/question/coordinator.py`
- 主要改动：
  - 接入 schema 归一化与审计结果生成，绑定 `source_refs`。

- 文件：`web/app/question/AssignmentReviewWorkspace.tsx`
- 主要改动：
  - 审核面板展示扩展质量指标（含溯源条数、干扰项指标）。

#### 3.17 相似题/变式题入口
- 文件：`web/app/question/AssignmentReviewWorkspace.tsx`
- 主要改动：
  - 在练习结果中提供“同知识点再练/升难度/降难度/变式”触发逻辑。

### Phase 6：存储演进与测试
#### 3.18 API 注册与系统接线
- 文件：`src/api/main.py`
- 主要改动：
  - 挂载 `assignment_review` 路由，接入统一 API 服务。

#### 3.19 测试补充
- 新增测试文件：
  - `tests/agents/question/test_generate_agent_distractor.py`
  - `tests/agents/question/test_quality.py`
  - `tests/agents/question/test_repository.py`
  - `tests/api/utils/test_assignment_review_repository.py`
  - `tests/api/utils/test_assignment_review_store_flow.py`
- 覆盖重点：
  - 干扰项筛选与答案标签有效性。
  - 题型/schema 归一化。
  - 仓储 JSON 持久化读写。
  - assignment-review 端到端存储流程（发布、提交、评审、错题、再练记录）。

## 4. 前端工作台重构结果（产品视角）
- 文件：`web/app/question/AssignmentReviewWorkspace.tsx`
- 结果概述：
  - 单页聚合三大场景：
    - 出题与练习（含考试模式）
    - 教师作业发布与评审
    - 学生作业提交与错题闭环
  - 核心操作全部中文化，支持批量导出和错题再练闭环。

## 5. 关键接口清单（新增）
### 5.1 作业评审域
- `POST /api/v1/assignment-review/teacher/rubric-draft`
- `GET /api/v1/assignment-review/teacher/assignments`
- `POST /api/v1/assignment-review/teacher/assignments`
- `POST /api/v1/assignment-review/teacher/assignments/{assignment_id}/confirm`
- `GET /api/v1/assignment-review/student/published`
- `GET /api/v1/assignment-review/student/submissions`
- `GET /api/v1/assignment-review/teacher/submissions`
- `POST /api/v1/assignment-review/student/submissions`
- `POST /api/v1/assignment-review/teacher/submissions/{submission_id}/review`
- `GET /api/v1/assignment-review/student/wrongbook`
- `POST /api/v1/assignment-review/student/wrongbook/{item_id}/practice`
- `POST /api/v1/assignment-review/student/wrongbook/custom`

### 5.2 出题域
- `POST /api/v1/question/evaluate/written`

## 6. 当前验证状态
- 已完成：
  - 关键后端文件语法检查通过（出题生成、质量模块、评分路由）。
  - 关键功能链路代码级联调已完成（发布->提交->评审->错题->再练）。
- 未完成：
  - 当前环境缺少 `pytest`/运行时依赖，未执行完整自动化测试套件。

## 7. 变更文件总览（本次报告覆盖）
- 后端：
  - `src/agents/question/agents/generate_agent.py`
  - `src/agents/question/coordinator.py`
  - `src/agents/question/quality.py`
  - `src/agents/question/repository.py`
  - `src/api/main.py`
  - `src/api/routers/question.py`
  - `src/api/routers/assignment_review.py`
  - `src/api/utils/assignment_review_repository.py`
  - `src/api/utils/assignment_review_store.py`
- 前端：
  - `web/app/layout.tsx`
  - `web/app/login/page.tsx`
  - `web/app/question/page.tsx`
  - `web/app/question/AssignmentReviewWorkspace.tsx`
  - `web/app/wrongbook/page.tsx`
  - `web/components/AppShell.tsx`
  - `web/components/Sidebar.tsx`
  - `web/components/question/LogDrawer.tsx`
  - `web/context/AuthContext.tsx`
  - `web/context/GlobalContext.tsx`
  - `web/context/question/QuestionContext.tsx`
  - `web/lib/persistence.ts`
  - `web/types/question.ts`
- 测试：
  - `tests/agents/question/test_generate_agent_distractor.py`
  - `tests/agents/question/test_quality.py`
  - `tests/agents/question/test_repository.py`
  - `tests/api/utils/test_assignment_review_repository.py`
  - `tests/api/utils/test_assignment_review_store_flow.py`

## 8. 结论
今晚改动已将出题模块从“单点出题能力”升级为“可发布、可提交、可评审、可沉淀错题、可再练、可导出”的教学闭环基础版本，并完成了 Phase 0~6 的核心骨架落地。后续可在当前基础上继续提升自动批改算法精度与 UI 细节打磨。
