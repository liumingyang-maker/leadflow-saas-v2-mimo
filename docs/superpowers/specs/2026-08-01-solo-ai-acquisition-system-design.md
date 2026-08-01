# LeadFlow 单人版 AI 获客系统完整技术方案

状态：产品方向与单人版收敛方案已确认，等待书面设计复核后同步实施计划

日期：2026-08-01

适用仓库：`leadflow-saas-v2-mimo`

当前产品阶段：单人/单组织内部使用，保留未来公共 SaaS 边界

文档类型：产品设计、渠道策略与技术架构，不代表已经实施

## 1. 决策摘要

LeadFlow 不应继续以“增加更多采集按钮”为核心，也不应把大模型当成可以直接操作 CRM
和自动群发的全权代理。推荐把产品核心升级为 **AI 获客任务（Acquisition Mission）**：

1. 用户只需选择产品、目标国家和买家类型；语言、排除词、渠道和预算由默认值或高级设置承担；
2. AI 规划查询词、语言、渠道组合和验证方法；
3. 渠道适配器只负责取得候选及原始来源；
4. 系统保存可追溯证据，用硬规则验证国家、业务类型、产品相关性和联系方式；
5. AI 负责解释、排序、生成个性化草稿，但不能自动确认事实；
6. 用户审核候选和首次发送；
7. 回复与审核结果形成结构化复盘和优化建议，由用户确认后改进下一次任务。

推荐的首期渠道不是最多，而是以下四类：

- 自有渠道：网站 Inbound、手工录入、CSV/XLSX；
- 有证据的网页研究：MiMo 联网搜索 + 企业官网验证；
- 稳定官方数据：Google Places API、YouTube Data API；
- 按需付费增强：Hunter、Apollo、合规的贸易数据供应商。

明确结论：

- **MiMo `mimo-v2.5` 作为单人版首选 AI 研究与草稿模型。**
- **GitHub 主要用于寻找可靠基础组件，不是驰象摩托车发动机业务的主要获客渠道。**
- **YouTube 是市场意向信号源，不是已验证联系人数据库。**
- **竞品雷达是正式获客模块。** 它监控竞品、经销网络和市场变化，并把经过证据验证的
  经销商转为 Candidate；不照搬旧版脆弱抓取实现。
- **旧版大量网页爬虫不恢复为核心能力。** 平台无官方/授权 API 时，只允许人工辅助或研究性使用。
- **静态 HTTP 取证是网页研究主路径，受控 Browser MCP 是按需增强。** 浏览器不可用时不得阻断核心获客闭环。
- **不做全自动发送。** AI 贯穿全流程，但外发、事实承诺、候选接受仍有人工门禁。

## 2. 产品目标与边界

### 2.1 单人版目标

系统要帮助一个外贸经营者完成一条可重复的闭环：

```text
产品事实
  -> 选择市场与买家类型
  -> 多渠道发现企业或购买意向
  -> 保存证据并验证
  -> 找到可联系渠道
  -> 排序与人工审核
  -> 生成事实受限的个性化邮件
  -> 人工批准发送
  -> 归档回复和下一步
  -> 用结果优化下一轮任务
```

成功标准不是“抓到多少条数据”，而是：

- 每个候选为什么可能购买都能解释；
- 每个事实都能点回来源；
- 用户能在较短时间内筛出真正值得联系的公司；
- 系统不虚构产品参数、价格、MOQ、认证或交期；
- 外发记录、退订和抑制规则继续生效；
- 将来转公共 SaaS 时不需要重写租户、任务、能力和审计边界。

### 2.2 首期不做

- 公共注册、套餐、支付、团队席位和多租户自助管理；
- 无人值守批量外发、自动接受 Lead、自动报价或自动承诺交期；
- LinkedIn 登录态爬取、TikTok/Facebook 页面爬取；
- Alibaba RFQ、Zauba、Europages 等页面结构依赖型批量爬虫；
- 同时接入四五个大模型并为每条候选做昂贵投票；
- 为单人使用引入微服务、Kubernetes、独立向量数据库或复杂 Agent 框架。

## 3. 当前系统基础与必须保留的设计

现有 V2 已经有正确的长期基础，本方案在其上扩展，不推倒重来：

| 现有能力 | 保留方式 |
|---|---|
| Flask 模块化单体 | 新增 `acquisition` 领域模块，不拆微服务 |
| `tenant_id` 隔离 | 所有新增业务表、Repository 和 Job 都显式带租户范围 |
| Capability Service | 新渠道和 AI 外发能力由命名 Capability 控制 |
| 持久化 Job + RQ/Redis | 所有耗时搜索、抓取、验证和 AI 请求进入 Job |
| Collection Adapter | 继续作为渠道标准化边界，增加证据输出契约 |
| Lead 审核与 CRM | 经过验证的候选才晋升到 Lead/CRM |
| Outreach | 复用 dry-run、配额、退订、抑制和审计 |
| Inbound | 保留已有安全、幂等和租户所有权边界 |
| Alembic | 只新增 revision，不修改已发布 migration |

当前实现有一个重要缺口：`Candidate` 是内存对象，Worker 会丢弃没有邮箱的候选并直接把有邮箱的
候选写为 `Lead`。真实网页研究经常先发现公司和官网，之后才找到联系人。因此需要新增持久化的
候选区，不能要求 AI 在第一次搜索时就“变出一个邮箱”。

现有 `OLD_TO_V2_MIGRATION_MATRIX.md` 把竞品雷达冻结到 V2 核心闭环之后。本设计在用户明确确认
竞品雷达价值后，提出在 Phase 2 正式解冻它；实施前应同步更新迁移矩阵/产品路线图，不能让两个
有效文档长期互相矛盾。

实施获客功能前还应先补齐 `AdminUser.auth_version` 的新 Alembic revision。当前模型已有字段，
但已发布 migration 链只给普通用户表增加了该字段。这个前置修复不能混入获客业务 migration。

## 4. 方案比较

### 方案 A：恢复旧版所有渠道爬虫

做法：恢复 Apollo、ImportYeti、Europages、Alibaba RFQ、Zauba、YouTube、TikTok、LinkedIn、
竞品雷达等全部旧采集器。

优点：页面上看起来渠道很多，短期演示效果强。

问题：

- 旧采集器缺少正式测试；
- 页面 HTML、反爬规则、登录状态和服务条款不断变化；
- 维护成本远高于单人版能获得的真实收益；
- 采集数量会掩盖匹配率、联系率和回复率；
- 很多所谓渠道只是同一批公开网页的不同入口。

结论：不采用。只保留经过重新评估的官方或授权接口。

### 方案 B：大模型全权 Agent

做法：给模型产品介绍和 API Key，让它自己搜索、判断、写入 Lead、生成并发送邮件。

优点：开发表面上最少，自动化感最强。

问题：

- 搜索结果和模型推理不能替代事实证据；
- 网页内容可能包含提示注入；
- 模型会把“可能将来需要”误判为当前购买意向；
- 重试可能重复写入或重复发送；
- 无法可靠解释错误是搜索、抽取、判断还是外发造成的。

结论：不采用。

### 方案 C：AI 获客任务 + 分层渠道 + 确定性门禁

做法：AI 负责规划、研究、抽取、解释和草稿；渠道适配器负责数据获取；业务服务负责验证、
幂等、状态和外发；用户批准高风险动作。

优点：

- AI 贯穿整个流程，但不会控制安全边界；
- 渠道可替换，MiMo 不是单点架构依赖；
- 每个候选有证据和拒绝理由；
- 适合单人版，也保留公共 SaaS 的租户、配额和审计入口；
- 可以先做一条完整闭环，再增加渠道。

代价：需要新增候选、证据和任务编排模型。

结论：**采用。**

## 5. 渠道可靠性模型

### 5.1 先判断渠道能提供什么

一个渠道只能承担以下一种或多种职责，不能把所有数据都叫 Lead：

| 职责 | 含义 | 示例 |
|---|---|---|
| 市场信号 | 判断国家、品类或需求是否值得投入 | UN Comtrade、行业新闻、YouTube 视频趋势 |
| 企业发现 | 找到可能匹配的公司 | 网页搜索、Google Places、Apollo Organization Search |
| 业务验证 | 证明公司确实经营相关产品 | 企业官网产品页、官方目录、注册信息 |
| 意向信号 | 证明某人在近期表达了相关需求 | YouTube 评论、询盘表单、公开 RFQ |
| 联系增强 | 为已验证企业找到联系人 | 官网 Contact 页、Hunter、Apollo |
| 触达渠道 | 向已审核联系人发送消息 | 电子邮件、人工 WhatsApp |

市场信号不能直接变成联系人，目录条目不能直接证明采购意向，模型推断也不能变成事实。

### 5.2 证据信任等级

| 等级 | 来源 | 可以证明什么 | 默认用途 |
|---|---|---|---|
| A | 企业官网、政府注册、官方平台 API | 企业身份、公开产品、公开联系方式 | 硬验证 |
| B | 授权/付费数据供应商、官方行业目录 | 公司、人员、贸易或联系数据 | 验证或增强 |
| C | 信誉较好的行业媒体、商会、展会目录 | 行业和参与信号 | 辅助验证 |
| D | 搜索摘要、社交评论、普通 B2B 页面 | 候选线索或意向线索 | 发现，必须再验证 |
| E | 大模型推断、未引用摘要 | 假设 | 只用于排序，不能当证据 |

候选进入“建议审核”至少满足：

- 一个 A 级来源；或
- 两个相互独立的 B/C 级来源；
- 并且有一个可用联系路径（邮箱、电话、联系页或公开业务账号）。

### 5.3 渠道优先级

#### P0：立即构成闭环

| 渠道 | 作用 | 可靠性 | 决策 |
|---|---|---:|---|
| 自有网站 Inbound | 已主动表达需求 | 很高 | 继续作为最高优先级 Lead |
| CSV/XLSX、手工录入 | 导入已有关系和展会数据 | 高，取决于来源 | 保留并补充来源说明 |
| 手工 URL 研究 | 用户给一个企业网址，AI 验证与摘要 | 很高 | 新增，是最低风险 AI 入口 |
| MiMo 联网搜索 | 多语言企业发现、查询规划 | 中 | 作为首选 Research Provider |
| 企业官网验证 | 证明产品、业务类型、地区与联系路径 | 高 | 所有网页候选的强制步骤 |

#### P1：可靠增量

| 渠道 | 作用 | 可靠性 | 决策 |
|---|---|---:|---|
| Google Places Text Search | 发现本地经销商、维修商、批发商 | 中高 | 使用官方 API，不解析 Maps HTML |
| YouTube Data API | 视频、频道和评论中的市场/购买意向 | 中 | 做“信号”，不直接生成已验证联系人 |
| 官网 Contact/About 抽取 | 获取公开业务邮箱、电话、WhatsApp 链接 | 高 | 只抓已确认官网的少量页面 |
| 竞品雷达 | 发现竞品经销网络、跨品牌大经销商和市场变化 | 中高 | 作为正式模块，共享 Candidate/Evidence，详见第 16 节 |

#### P2：有数据后按收益接入

| 渠道 | 作用 | 判断 |
|---|---|---|
| Hunter | 已知公司域名后的公开邮箱查找与验证 | 比盲搜更适合当前业务，优先于大规模人员库 |
| Apollo | 按公司、职位、地区找决策人并增强 | 对大中型企业有效；小型区域经销商覆盖可能有限 |
| 付费贸易数据 | 公司级进口记录与采购能力 | 价值高但成本高，先用小样本验证 ROI |
| 商会/展会/政府目录 | 行业企业列表 | 每个国家单独评估，优先官方可下载数据 |

UN Comtrade 适合判断“哪个国家、哪个 HS 类目在增长”，不应被描述成公司联系人来源。
免费宏观数据与公司级进口商名单是两种不同产品。

#### P3：研究性渠道

- Europages、Kompass、行业媒体和普通 B2B 目录：通过搜索发现，人工或官网二次验证；
- 新闻、招聘和新品动态：作为时间性信号，不作为主身份来源；
- GitHub：若未来销售开发者工具可作为企业信号；对当前摩托车发动机业务不应列为获客渠道。

#### Deferred/Blocked

- LinkedIn 登录态搜索或页面爬取；官方开放接口主要服务已授权的营销、页面和合作伙伴场景，
  不等同于公共人员搜索 API；
- TikTok Research API 面向符合条件的非商业研究者，不适合作为商业获客后端；
- Facebook/Instagram 未授权页面批量抓取；
- Alibaba RFQ、Zauba、Europages HTML 定制爬虫；
- `yt-dlp` 作为常驻生产获客器；
- 大规模冷邮件和自动 WhatsApp 群发。

WhatsApp 在本方案中属于触达渠道，不是企业发现渠道。首期只保存企业官网明确公开的 WhatsApp
业务链接，并由用户人工发起；未来若接入 Cloud API，也必须把模板、用户同意和外发策略作为
单独能力审查，不能因为有电话号码就自动发送。

### 5.4 新渠道准入评分卡

以后不是发现一个 GitHub 项目或旧版采集器就直接加进菜单。每个新渠道先登记 `ChannelProfile`，
再用同一评分卡评估：

| 维度 | 权重 | 核心问题 |
|---|---:|---|
| 数据可靠性 | 25 | 是否有稳定 API、稳定 ID、来源时间和明确字段定义？ |
| 目标市场适配 | 20 | 是否真的覆盖本产品的国家、买家类型和公司规模？ |
| 身份与证据 | 15 | 能否回到官网、注册信息或可验证来源？ |
| 可联系性 | 15 | 能否合法取得业务联系路径，还是只有公司名？ |
| 访问与政策风险 | 10 | 是否有官方/授权方式，条款是否允许当前用途？ |
| 成本效率 | 10 | 每个被接受 Candidate 和积极回复的成本是多少？ |
| 维护成本 | 5 | 页面变化、验证码、代理和浏览器维护是否可控？ |

准入流程：

```text
渠道提案
  -> 文档与条款核对
  -> Adapter 假实现和契约测试
  -> 最多 50 个候选的隔离试点
  -> 人工统计精确率/联系率/成本
  -> 通过阈值后进入 P1/P2
  -> 连续低质量或频繁故障时降级/停用
```

访问方式不清楚、不能保存来源或目标市场覆盖不足时，即使总分看起来较高也直接否决。

## 6. GitHub 调研后的组件取舍

GitHub 上成熟项目能提升网页取证能力，但不能把不稳定或不被允许的访问方式变成可靠渠道。

| 项目 | 优点 | 风险/成本 | 本方案决定 |
|---|---|---|---|
| Scrapy | 成熟、BSD-3-Clause、适合大规模结构化爬取 | 对单人版少量官网验证过重 | 不在 P0 引入；稳定批量站点出现后再评估 |
| Crawl4AI | Apache-2.0、LLM 友好、浏览器与 Markdown 输出 | 浏览器依赖重，近期曾有多项 Docker API 安全修复 | 只允许在隔离 Worker 中作为 P2 可选 Fetcher |
| Firecrawl | 搜索、抓取、清洗和托管能力完整 | 自托管仓库 AGPL，云服务有成本与供应商依赖 | 可做后续托管适配器，不做核心依赖 |
| SearXNG | 自托管元搜索、可组合多个搜索源 | AGPL、需运维，底层引擎规则仍会变化 | 只作为搜索故障备用，不在首期部署 |
| Playwright | 能处理必要的 JavaScript 页面 | 慢、脆弱、攻击面更大 | 只作为已批准官网的最后一级回退 |
| Google API Python Client | YouTube 等 Discovery API 的 Google 官方客户端 | 包较大且处于维护模式 | 可用；也可直接用受控 HTTP 客户端调用 YouTube API |

P0 的网页策略应尽量简单：

1. 优先使用模型返回的引用 URL；
2. 对确认的官网使用受限 HTTP Fetcher 获取少量 Contact/About/Product 页；
3. 静态解析失败才进入浏览器 Worker；
4. 不做全站深爬，不绕 robots、登录或访问限制；
5. 所有 Fetcher 都实现相同协议，后续才能替换成 Firecrawl/Crawl4AI。

## 7. MiMo 能力验证结论

本方案基于真实 API 小样本，而不是只看模型宣传：

| 测试 | 结果 | 设计含义 |
|---|---|---|
| 基础 API | HTTP 200，约 1.75 秒，按要求输出固定文本 | 连通性和基本调用通过 |
| 简单联网搜索 | 触发 1 次搜索、读取 3 页，约 20.94 秒 | 能执行搜索并输出结构化结果 |
| 事实 ID 约束草稿 | `mimo-v2.5` 约 4.65 秒、596 tokens | 能使用允许事实并拒绝不可信产品声明 |
| 严格候选发现 | 2 次搜索、10 页、约 36.47 秒、3017 tokens | 能找出真实企业和引用来源 |
| 严格候选人工复核 | 2 个候选中 1 个真正匹配 | 不能自动接受，必须有硬规则和证据复核 |

失败样本很有代表性：模型把一家只经营电动摩托车的企业解释成“将来可能需要燃油发动机”。
这不是网页不存在，而是模型从事实跳到了销售愿望。因此系统必须把以下字段分开：

- `observed_facts`：来源明确写出的事实；
- `inferences`：模型推断；
- `unknowns`：目前无法确认；
- `rejected_claims`：明确禁止用于外发的说法。

首期使用 `mimo-v2.5`，不默认使用 Pro。当前小样本中普通版本的事实约束表达更干净、成本更低。
但模型名必须配置化，不能写死在业务逻辑中。

## 8. 端到端获客流程

```mermaid
flowchart TD
    A["Approved Product Knowledge\n驰象官网与人工确认事实"] --> B["找客户任务\n产品/国家/买家类型"]
    B --> C["AI Planner\n生成查询与渠道计划"]
    C --> D["Channel Adapters\nWeb / Radar / Places / YouTube / Import"]
    D --> E["Persistent Candidates\n先保存公司与信号"]
    E --> F["Static HTTP Evidence\n公开静态网页主路径"]
    F --> Q{"确需动态页面?"}
    Q -->|否| R["Evidence Verification\n官网/地区/产品/买家类型"]
    Q -->|是且策略允许| S["Isolated Browser Worker\n受控只读增强"]
    Q -->|不可用或禁止| T["Needs Evidence\n保留已有结果"]
    S --> R
    R --> G{"Hard Eligibility Gates"}
    G -->|不通过| H["Rejected with Reason"]
    G -->|通过| I["AI Ranking & Explanation"]
    I --> J["Human Review Queue"]
    J -->|接受| K["Contact Enrichment"]
    J -->|拒绝| H
    K --> L["Promote to Lead / CRM"]
    L --> M["Fact-bound Draft"]
    M --> N["Human Send Approval"]
    N --> O["Outreach + Inbound Reply"]
    O --> P["Feedback Metrics"]
    P --> B
```

### 8.1 创建任务

首屏只有三个必填字段：

- 产品：从已批准的产品知识中选择，可默认上一次使用项；
- 目标国家：ISO 国家下拉，可多选，但执行时拆成单国 run；
- 买家类型：进口商、经销商、批发商、装配厂或维修网络等预设项。

语言由国家默认值推导；行业、公司规模、包含词、排除词、渠道、候选数、搜索次数、时间和费用预算
全部放入折叠的“高级设置”。用户也可以输入自然语言目标，由 AI 解析为上述字段，但必须先展示解析结果并
由用户确认，不能解析后立即运行。

AI 返回可编辑计划：目标假设、查询词、当地语言同义词、渠道顺序、验证标准和停止条件。
计划只是草稿，业务服务会校验预算和允许渠道。

### 8.2 发现与保存

每个适配器返回统一候选，但新合同应允许“公司优先、联系人稍后”：

```python
class DiscoveryCandidate:
    external_id: str
    entity_type: Literal["company", "person", "intent_signal"]
    company_name: str
    domain: str
    website: str
    country: str
    source: str
    source_url: str
    observed_fields: dict
    evidence: list[EvidenceInput]
```

不得把完整第三方响应、原始 HTML、Cookie、API Key 或模型隐藏推理写入 Candidate。

### 8.3 验证

验证按顺序执行，避免把模型预算浪费在明显不合格数据上：

1. URL 规范化和域名去重；
2. 国家/地区硬过滤；
3. 排除市场平台、搜索页、社交聚合页和供应商页；
4. 确认独立官网或足够的独立来源；
5. 提取企业自述、产品、服务和联系方式；
6. 检查买家类型和排除项；
7. AI 生成结构化说明；
8. 独立规则验证 AI 输出与引用是否一致；
9. 通过后进入人工队列；国家未知或证据冲突时进入“待确认国家”，不直接拒绝。

### 8.4 晋升 Lead

候选和 Lead 是两个状态层：

- Candidate 可以只有公司、官网或意向信号；
- Lead 是已审核、值得跟进的 CRM 对象；
- 接受 Candidate 时通过幂等服务创建或合并 Lead；
- Lead 可以先只有官网/电话/联系页，不强制伪造邮箱；
- 联系增强是后续动作，并且保留来源与验证日期。

### 8.5 外发与反馈

AI 草稿只能引用产品知识库中的事实 ID，以及候选证据中的公开事实。外发前显示：

- 使用了哪些产品事实；
- 使用了候选的哪些来源；
- 哪些字段仍未知；
- 是否包含价格、认证、MOQ、交期等高风险内容；
- 收件人、退订和抑制状态。

首封、批量发送和任何包含商业承诺的内容必须人工确认。回复可以由 AI 分类和建议下一步，
但报价、合同、付款和承诺仍由用户决定。

### 8.6 反馈闭环

每次接受、拒绝、补证、联系、积极回复、消极回复、无回复、成交和流失都保存结构化结果。系统自动
聚合模式，但首期只生成建议，不自动改变搜索或评分策略：

- 同一拒绝原因累计至少 5 次，或占本次已审核候选 30% 以上时，建议增加排除条件；
- 同一买家类型累计至少 10 次被接受时，建议提高下次任务中的偏好；
- 至少有 30 个带明确结果的候选后，才允许提出评分权重调整建议；
- 应用建议时复制为新的 Mission/Profile/Score Version，并保留旧版本与撤回入口；
- 自动统计和提出建议不需要确认，应用排除词、买家偏好或权重必须由用户确认；
- 系统不得根据少量拒绝自动拒绝未来候选，也不得因为反馈自动发送外联。

## 9. 模块与接口设计

### 9.1 新模块边界

```text
app/modules/acquisition/
  models.py          # Mission、Candidate、Evidence、Assessment
  repository.py      # 全部 tenant-scoped
  service.py         # 状态机、晋升、幂等与硬规则
  routes.py          # Web/HTMX 入口
  policies.py        # eligibility、预算、渠道策略

app/modules/radar/
  models.py          # 竞品、网络关系、快照和变化事件
  repository.py      # tenant-scoped watchlist 与查询
  service.py         # 扫描、diff、事件确认和 Candidate 转换
  routes.py          # 雷达总览、竞品详情、变化审核

app/integrations/research/
  contracts.py       # ResearchProvider、SourceFetcher
  mimo.py            # MiMo 联网搜索
  website.py         # 受限官网抓取
  youtube.py         # YouTube Data API
  google_places.py   # Places Text Search
  hunter.py          # 后续联系增强
  apollo.py          # 后续组织/人员增强

app/integrations/radar/
  contracts.py       # RadarSource 与观察结果契约
  official_site.py   # 竞品官网、Where-to-Buy/Dealer 页面
  reverse_search.py  # 本地化反向经销商搜索
  trade_signal.py    # 官方/授权贸易数据，首期可禁用

app/integrations/ai/
  contracts.py       # Planner、Extractor、Ranker、Drafter
  prompts/           # 版本化 prompt 与 JSON Schema
  provider_router.py # 配置、健康检查与显式回退
```

### 9.2 不使用一个“万能 LLM 接口”

模型调用按职责拆分，才能给每个输出不同约束：

```python
class MissionPlanner(Protocol):
    def plan(self, request: MissionRequest) -> MissionPlan: ...

class ResearchProvider(Protocol):
    def search(self, request: ResearchRequest) -> ResearchResult: ...

class CandidateExtractor(Protocol):
    def extract(self, evidence: EvidenceBundle) -> CandidateFacts: ...

class CandidateRanker(Protocol):
    def rank(self, facts: CandidateFacts, target: TargetProfile) -> Ranking: ...

class OutreachDrafter(Protocol):
    def draft(self, product_facts: FactBundle, lead_facts: FactBundle) -> Draft: ...
```

这些接口返回 Pydantic/JSON Schema 验证后的结构；模型不能获得数据库 Session，也不能直接调用发送服务。

### 9.3 渠道适配器输出升级

现有 `CollectionResult` 继续保留给 CSV/XLSX 和已有 Job。新发现适配器需要额外返回：

- `provider_request_id`；
- 使用次数和 token/搜索页统计；
- 标准化引用 URL；
- 证据标题、短摘要、抓取时间和来源类型；
- 安全错误码；
- 是否可能重试；
- 是否部分成功。

不得通过 `metadata_json` 无限堆积所有第三方原始响应。

### 9.4 Capability 建议

单人版仍使用集中能力服务，建议新增：

- `AI_RESEARCH`
- `WEBSITE_EVIDENCE_FETCH`
- `BROWSER_RESEARCH`
- `YOUTUBE_DISCOVERY`
- `PLACES_DISCOVERY`
- `CONTACT_ENRICHMENT`
- `AI_OUTREACH_DRAFT`
- `COMPETITOR_RADAR`

真实发送继续复用已有 `OUTREACH_SEND`，不能以“AI 草稿能力已开启”推导发送权限。内部默认只开启
Phase 1A 所需的 `AI_RESEARCH`、`WEBSITE_EVIDENCE_FETCH` 和 `AI_OUTREACH_DRAFT`；
`BROWSER_RESEARCH` 默认关闭，只在 Phase 1B 的运行时、策略和恢复门禁全部就绪后显式启用；其他能力随
对应阶段单独启用。

## 10. 数据模型

### 10.1 `acquisition_missions`

| 字段 | 说明 |
|---|---|
| `id`, `tenant_id` | UUID 与租户所有权 |
| `name` | 用户可识别名称 |
| `status` | `draft/queued/running/paused/completed/failed/cancelled` |
| `product_snapshot_id` | 固定本次任务使用的产品事实版本 |
| `target_profile_json` | 国家、语言、买家类型、排除项 |
| `channel_policy_json` | 允许渠道和顺序 |
| `budget_json` | 搜索次数、候选数、token/费用上限 |
| `plan_json` | 用户批准后的 AI 计划 |
| `cost_summary_json`, `retrospective_json` | 任务成本、审核原因与结果复盘快照 |
| `created_by`, timestamps | 审计 |

### 10.2 `acquisition_candidates`

| 字段 | 说明 |
|---|---|
| `id`, `tenant_id`, `mission_id` | 归属 |
| `entity_type` | `company/person/intent_signal` |
| `status` | `discovered/verifying/needs_evidence/eligible/rejected/accepted/promoted` |
| `company_name`, `domain`, `website` | 标准化企业字段 |
| `hq_country_code`, `opportunity_country_code`, `contact_country_code` | 总部、机会市场和联系人国家，含义不得混用 |
| `country_resolution_status` | `unknown/confirmed/conflicting` |
| `source_channel`, `source_provider` | 例如 `competitor_radar/mimo`，不依赖自由文本 notes |
| `contact_json` | 已公开的联系点，首期保持小型 JSON |
| `observed_facts_json` | 只存来源观察事实 |
| `inferences_json` | AI 推断，与事实分开 |
| `unknowns_json` | 缺失项 |
| `eligibility_code` | 硬门禁结果 |
| `priority_score`, `priority_band`, `signal_coverage`, `ai_confidence` | 分离业务评分、证据覆盖和模型自信 |
| `decision_reason_code`, `decision_note`, `decided_at` | 结构化人工审核反馈 |
| `dedupe_key` | `tenant + canonical_domain` 等稳定键 |
| `promoted_lead_id` | 晋升后关联 Lead |
| timestamps | 审计与过期处理 |

建议唯一约束：`(tenant_id, mission_id, dedupe_key)`。跨任务发现同一企业时不删除历史，
而是关联到已有公司/Lead 并新增 evidence。

### 10.3 `candidate_evidence`

| 字段 | 说明 |
|---|---|
| `id`, `tenant_id`, `candidate_id`, `job_id` | 归属与执行来源 |
| `provider`, `source_type`, `trust_tier` | 来源分类 |
| `source_url`, `canonical_url` | 可点击证据 |
| `title`, `excerpt` | 经清洗和限长的内容 |
| `observed_at`, `retrieved_at`, `expires_at` | 时效性 |
| `content_hash` | 变更和重复判断 |
| `supports_json` | 该证据支持哪些结构化 claim |
| `validation_status` | `unverified/valid/stale/unreachable/contradicted` |

### 10.4 `product_knowledge_snapshots`

| 字段 | 说明 |
|---|---|
| `id`, `tenant_id`, `version` | 版本化知识快照 |
| `source_revision` | 官网版本、内容 revision 或人工版本号 |
| `facts_json` | `fact_id/text/category/language/source_url/status` |
| `prohibited_claims_json` | 价格、MOQ、认证等未批准内容 |
| `approved_by`, `approved_at` | 人工批准 |
| `content_hash` | 不可变性检查 |

任务创建后引用快照，不随官网编辑自动改变，保证过去的草稿可解释。

### 10.5 `candidate_assessments`

保留每次规则/模型版本的审核结果：`candidate_id`、`policy_version`、`prompt_version`、
`model_provider`、`model_id`、`evidence_bundle_hash`、`input_json`、`hard_gate_json`、
`score_breakdown_json`、`signal_coverage`、`priority_mode`、`explanation`、时间戳。
这对比较 MiMo 与未来其他模型非常重要。

Assessment 幂等键至少包含：

```text
tenant_id + candidate_id + evidence_bundle_hash + policy_version
          + score_version + prompt_version + model_id
```

### 10.6 `mission_suggestions`

保存半自动反馈建议，而不是直接改写 Mission：`tenant_id`、`mission_id`、`suggestion_type`、
`reason_codes_json`、`sample_size`、`proposed_change_json`、`status=proposed/applied/dismissed`、
`applied_profile_version` 和时间戳。建议可重复计算，但应用动作必须幂等并记录操作者。

### 10.7 `browser_site_policies`

Phase 1B 使用。租户级域名策略保存 `canonical_domain`、`access_mode`、条款/robots 复核状态、允许的
origin/path、页数/时间/延迟预算、批准人和复核时间。系统级 blocked 域名由代码维护，优先级高于数据库，
不能通过普通设置覆盖。

### 10.8 `browser_research_runs`

一行对应一个实际浏览器会话，关联 Mission/Candidate/Job，保存起始/最终 URL 的安全版本、域名、策略
决定、页数、工具次数、字节数、状态、错误码、`heartbeat_at`、lease、制品目录引用和开始/结束时间。
状态为 `queued/running/completed/partial/blocked/failed/cancelled`。表不保存 Cookie、完整 HTML、完整
第三方响应或模型隐藏推理。

普通 Worker 持有 MiMo 会话和业务策略，通过带 run-scoped token 的内部请求/响应通道向 Browser Worker
发送已经校验的高层只读动作。Browser Worker 只消费最小 run descriptor、执行 allowlist 动作并返回清洗
结果/受限制品；它不持有数据库和 SecretStore 凭据。MiMo 调用、Evidence 校验与数据库写入由普通
Worker 完成，避免浏览器进程同时拥有外网浏览、应用数据和密钥权限。

## 11. 状态机与 Job 设计

### 11.1 Mission 状态

```text
draft -> queued -> running -> completed
                   |   |
                   |   -> paused -> queued
                   -> failed
queued/running/paused -> cancelled
```

只有业务服务能转换状态。Worker 重启后从数据库恢复，RQ 只携带 `job_id`。

### 11.2 Candidate 状态

```text
discovered -> verifying -> eligible -> accepted -> promoted
                 |            |
                 |            -> rejected
                 -> needs_evidence -> verifying
                 -> rejected
```

`rejected` 必须有机器可统计的原因。`country_unknown/country_conflicting` 不属于拒绝原因，而是
`needs_evidence` 子状态，补证或人工确认后重新进入 `verifying`：

- `wrong_country`
- `wrong_buyer_type`
- `electric_only`
- `supplier_not_buyer`
- `marketplace_not_company`
- `no_independent_domain`
- `insufficient_product_evidence`
- `no_contact_path`
- `duplicate`
- `stale_source`
- `manual_reject`

### 11.3 BrowserRun 状态

```text
queued -> running -> completed
             |  |-> partial
             |  |-> blocked
             |  |-> failed
             |  -> cancelled
             -> queued（仅明确 transient 错误创建新 attempt）
```

重试不复用旧浏览器上下文；旧 attempt 必须先终止并保留终态。策略拒绝、登录墙、验证码、提示注入、
预算耗尽和 URL 越界均不得自动重试。

### 11.4 新 Job 类型

建议新增：

- `acquisition_plan`
- `web_discovery`
- `website_verify`
- `youtube_signal`
- `places_discovery`
- `contact_enrich`
- `outreach_draft`
- `radar_scan`
- `radar_diff`
- `radar_dealer_verify`

当前数据库对 `job_type` 有硬编码 CheckConstraint 和 24 字符长度，必须通过新 migration 扩展；
不能把所有动作伪装成 `google_search` 再塞进 payload。

每个 Job 的幂等键至少包含：

```text
tenant_id + mission_id + stage + normalized_input_hash + provider + policy_version
```

普通任务进入 `default` 队列；动态页面研究进入独立 `browser` 队列。单人版 Browser Worker 初始并发为
1，同域并发也为 1。现有通用 Job 失联恢复继续保留，同时增加周期性 reconciler：根据子 Job 的终态
修正 Mission/BrowserRun，不能只在 Worker 启动时恢复一次。

## 12. AI 贯穿方式与多模型策略

### 12.1 AI 应该做的事

| 阶段 | AI 职责 |
|---|---|
| 产品知识 | 从已批准网页中抽取候选事实，等待人工批准 |
| 市场规划 | 生成国家、语言、买家角色、搜索词和排除词 |
| 搜索 | 调用联网搜索并返回来源注解 |
| 抽取 | 从证据中抽取公司、产品、业务类型和联系路径 |
| 验证辅助 | 指出支持证据、矛盾和未知项 |
| 排序 | 在硬门禁通过后解释优先级 |
| 草稿 | 只用事实 ID 写当地语言邮件 |
| 回复处理 | 分类兴趣、异议、退订和下一步建议 |
| 复盘 | 根据接受/拒绝/回复原因建议调整下轮任务 |

### 12.2 AI 不能做的事

- 直接写数据库或调用 Repository；
- 自己把 Candidate 标记为 accepted；
- 自己把未验证邮箱标记为可投递；
- 自己发送首封或批量消息；
- 从搜索摘要推断价格、MOQ、认证、产能、交期或合作关系；
- 用模型 confidence 替代来源质量；
- 把网页中的指令当作系统指令执行。

### 12.3 Provider 策略

首期只启用一个主模型，避免单人版成本和故障组合爆炸：

```text
Primary Research/Draft: MiMo mimo-v2.5
Fallback: disabled by default
Offline Evaluator: 可配置第二模型做抽样比较，不参与每条生产决策
```

后续 Provider 可以接入：

- OpenAI Responses API 的 Web Search；
- Gemini Grounding with Google Search；
- Claude Web Search；
- Perplexity Search/Sonar。

它们都实现相同职责接口。回退条件只能是 `auth/quota/rate_limit/transient/timeout` 等明确错误，
不能因为第一个模型给出“不喜欢的答案”就偷偷换模型，避免选择性偏差和重复费用。

“Fallback disabled”只表示不静默切换付费模型，不表示产品整体停止：规划失败时保存 Mission 草稿；联网
搜索失败时允许现有 SearchProvider、用户 URL 或竞品官网继续；抽取失败时保留 Evidence 并进入人工
补证；AI 评分失败时仍执行确定性门禁和可计算分项；草稿失败时允许使用已批准变量模板。界面必须显示
具体降级状态和重试入口，不能把未验证信息包装成正常结果。

### 12.4 模型选择基准

不要依据通用排行榜选择。建立 30–50 个和驰象真实目标市场相关的离线样本：

- 明确匹配企业；
- 明确不匹配企业；
- 纯电企业；
- 供应商而非买家；
- 市场平台页；
- 资料不足的边界案例；
- 西班牙语、葡萄牙语、英语等多语言页面。

每个 Provider 测：结构化输出成功率、引用可访问率、候选精确率、漏检率、事实越界率、
延迟和每个合格候选成本。模型只有在同一数据集上明显更好时才替换。

## 13. 产品知识库设计

驰象网站是产品事实的主要来源，但网页仍在设计中，因此采用两步发布：

1. AI 从已发布或指定页面生成“候选事实”；
2. 用户在后台确认后发布为 `ProductKnowledgeSnapshot`。

事实格式示例：

```json
{
  "fact_id": "F-MOTO-001",
  "category": "product_scope",
  "text": "供应摩托车发动机",
  "language": "zh-CN",
  "source_url": "https://approved.example/product",
  "status": "approved"
}
```

网页外部内容只能描述潜在客户，不能覆盖产品事实。比如某个目录写“支持五年质保”，
它也不能成为驰象自己的质保承诺。

高风险类别默认禁止，除非在知识快照中单独批准：

- 价格、折扣和付款条款；
- MOQ；
- 交期、库存和产能；
- 认证、测试报告和合规声明；
- 质保年限；
- 排量和型号兼容性；
- 当地售后、独家代理和客户案例。

## 14. 硬门禁、评分与去重

### 14.1 先门禁，后评分

以下任一条件失败，不能因为 AI 给了高分而进入推荐队列：

- 国家不符；
- 国家未知或来源冲突时不通过推荐门禁，但进入 `needs_evidence`，不进入 `rejected`；
- 明确属于排除业务，例如本任务排除纯电；
- 是供应商、市场平台或媒体而不是目标买家；
- 没有独立身份来源；
- 产品相关性只来自模型推测；
- 没有任何联系路径；
- 已在抑制/拒绝/重复名单。

### 14.2 `score-v1` 四类评分

通过门禁后分别计算 Fit、Intent、Data Quality，再合成 Priority。评分输入必须标明来源和是否已知；
未知值使用 `None`，不能用 0 或 50 冒充事实：

| 分数 | 组成 |
|---|---|
| Fit | 产品相关 35%、买家角色 25%、国家匹配 20%、公司规模 10%、行业匹配 10% |
| Intent | 直接购买信号 40%、近期活动 25%、竞品/经销信号 20%、信号时效 15% |
| Data Quality | 身份质量 25%、来源可信度 25%、可联系性 20%、独立证据 15%、数据时效 15% |
| Priority | `round(0.50 * Fit + 0.30 * Intent + 0.20 * DataQuality)` |

等级为 `S >= 85`、`A >= 70`、`B >= 55`、`C < 55`。模型的 `ai_confidence` 单独展示，不参与
硬门禁或 Priority。初始审核重点可设为 A/S，但阈值和权重只能根据真实接受率、联系率和回复率以新
score version 调整，不能重写历史 Assessment。

每个分项按已知子信号重新归一化，并计算 `signal_coverage`。Intent 完全未知时，按原权重对 Fit 与
Data Quality 重新归一化，标记 `priority_mode=fit_quality_provisional_v1`，界面显示“暂无意向信号”，
不能显示“意向低”。总覆盖不足 60% 时 Priority 仅为暂定，最高不能标为 S。可复现性要求是“相同的
持久化 ScoreInput 必须得到完全相同的分数”，不是要求重新调用大模型得到逐字一致的抽取结果。

### 14.3 去重

优先级：

1. 规范化根域名；
2. 已验证邮箱精确匹配；
3. E.164 电话精确匹配；
4. Provider 稳定 ID；
5. 公司名 + 国家模糊候选，仅提示人工合并，不自动合并。

不得复用 CRM 的模糊全文搜索来判断精确邮箱重复。

## 15. YouTube 渠道设计

### 15.1 为什么值得做

YouTube 上的评测、维修、经销、货运三轮车和当地品牌视频，能帮助发现：

- 哪些产品和车型在当地活跃；
- 哪些频道属于经销商、维修网络或行业媒体；
- 评论中是否出现价格、批发、进口、配件、发动机和代理询问；
- 视频描述中公开的企业官网和业务联系方法。

### 15.2 官方 API 流程

```text
本地语言关键词
  -> search.list 找视频/频道
  -> videos/channels.list 获取基础元数据
  -> commentThreads.list 获取公开评论
  -> AI 标注意向类别
  -> 规则识别企业网站/业务身份
  -> 官网二次验证
  -> 保存为 intent_signal 或 company candidate
```

官方文档当前说明 `search.list` 使用独立搜索配额桶，默认每天 100 次调用；
`commentThreads.list` 每次 1 单位。单人版默认每天最多使用 10 次搜索，缓存查询结果，
只对高相关视频拉取评论，避免无意义消耗。

### 15.3 允许保存

- 视频 ID、标题、URL、发布日期；
- 频道 ID、标题和公开 URL；
- 评论 ID、公开文本、时间和永久链接；
- AI 意向标签及其 prompt/model 版本；
- 评论或描述中明确公开的企业网站。

### 15.4 不允许推断

- 频道名等于公司法人名；
- 评论者就是采购决策人；
- 评论者的私人邮箱或电话；
- “多少钱”一定代表批量采购；
- 观看量等于购买意向。

只有当频道 About、视频描述或外部官网能证明企业身份时，信号才可以晋升为公司候选。

## 16. 竞品雷达完整设计

### 16.1 产品定位

竞品雷达不是单纯“盯着竞品看”，它有三个可执行输出：

1. **竞品情报**：品牌、产品类别、主力型号、目标国家和公开市场动作；
2. **渠道网络**：竞品官方经销商、公开销售该品牌的当地商家、跨品牌大经销商；
3. **变化机会**：新增/移除经销商、新增国家或型号、联系信息变化，并转成可审核 Candidate。

对驰象业务最有价值的不是竞品新闻，而是竞品已经教育并服务过的销售渠道。这些企业已经理解
摩托车、货运三轮车、发动机或配件市场，比全网盲搜更接近理想客户。

### 16.2 三种迁移方案

#### 方案 R1：原样复制旧版雷达

保留四源并行和所有旧代码，包括社媒、电商、公开海关聚合页抓取、线程调度和 AI 自动入库。

优点：最快恢复旧页面。

问题：旧实现把搜索摘要、网页抓取和模型评分混成一个类；社媒与电商页面不稳定；Web 进程内
调度不可恢复；按公司名和国家去重容易误合并；模型分数达到阈值就自动入库，证据门槛不足。

结论：不采用。

#### 方案 R2：不设雷达模块，只做普通 Mission

把竞品名称当成普通搜索关键词，结果都进入通用 Candidate。

优点：数据模型最少。

问题：无法表达竞品、经销商、国家和型号之间的长期关系，也无法稳定保存快照、变化和监控频率。

结论：不采用。

#### 方案 R3：独立雷达领域 + 共享获客基础设施

用 `app.modules.radar` 管理竞品档案、网络关系和变化事件；搜索、证据、Candidate、Job、AI、
联系增强和 Lead 晋升继续复用获客系统。

优点：保留旧版真正有价值的产品洞察，同时去掉重复代码和不可靠边界。

结论：**采用。**

### 16.3 旧版功能保留与重做

| 旧版能力 | 新版决定 |
|---|---|
| 手工添加竞品官网 | 保留，并强制验证为独立竞品域名 |
| 自动发现同类竞品 | 保留，由 MiMo 规划、本地化搜索、官网证据验证 |
| 反向经销商搜索 | 保留，作为主发现方式之一 |
| 多语言 distributor/dealer/importer 同义词 | 保留，改为版本化查询词典 + AI 建议 |
| 竞品官网 Where-to-Buy/Dealer 页面 | 保留，作为最高等级关系证据 |
| 型号作为搜索钥匙 | 保留，品牌名过泛时优先型号 + 产品类别 |
| 同一经销商代理多个竞品时加权 | 保留，但使用域名实体合并，不用公司名直接合并 |
| 电话/WhatsApp 优先 | 保留公开业务联系路径，不自动发送 |
| 情报卡、定期监控和 diff | 保留，改用规范化观察与事件表 |
| 社交/电商 HTML 批量抓取 | 不保留；改为官方 API、联网搜索信号或人工链接 |
| 公开海关聚合页抓取 | 不保留；改用授权贸易 Provider |
| AI 高分自动入库 Lead | 不保留；必须通过证据门禁并人工审核 |
| Web 进程内后台线程 | 不保留；使用持久化 Job 和外部定时触发 |
| 公司名 + 国家去重 | 不保留；改用规范化域名和稳定 Provider ID |

### 16.4 雷达来源分层

| 来源 | 能证明什么 | 信任等级 | 使用方式 |
|---|---|---:|---|
| 竞品官网 Dealer/Distributor 页面 | 官方渠道关系 | A | 直接建立 `official_distributor` 关系 |
| 经销商自己官网的品牌/产品页面 | 商家公开销售竞品 | A | 建立 `sells_brand`，记录具体页面 |
| Google Places 官方 API | 当地企业身份、地址和业务类别 | B | 验证企业与地点，不证明代理授权 |
| YouTube 官方 API | 经销、维修、评测或市场活动信号 | C/D | 发现后回到企业官网验证 |
| MiMo 联网搜索引用 | 候选页面、新闻和目录入口 | D | 只负责发现，不能单独确认关系 |
| 展会、商会、政府目录 | 参展和行业身份 | B/C | 辅助验证 |
| 授权贸易数据 | 进口品牌/品类关系 | B | 建立 `imports_brand/category`，注明数据周期 |
| 普通社媒/电商页面 | 在售或提及信号 | D | 人工或搜索辅助，不常驻抓取 |

“经销商销售竞品”与“竞品官方授权经销商”必须是两种不同关系，UI 和外发都不能混淆。

### 16.5 数据流

```mermaid
flowchart TD
    A["Competitor Watchlist\n品牌/官网/类别/国家"] --> B["Radar Planner\n品牌名+型号+本地语言查询"]
    B --> C["Official Site Scanner"]
    B --> D["Reverse Web Search"]
    B --> E["Places / YouTube / Trade Signals"]
    C --> F["Normalized Observations"]
    D --> F
    E --> F
    F --> G["Entity Resolution\n竞品/经销商/域名"]
    G --> H["Network Edges\n关系+证据+置信度"]
    H --> I["Snapshot & Diff"]
    I --> J["Radar Events\n新增/移除/变化"]
    J --> K{"Opportunity Gate"}
    K -->|通过| L["Acquisition Candidate"]
    K -->|不足| M["Needs Evidence"]
    L --> N["人工审核 -> Lead"]
```

### 16.6 核心数据模型

#### `competitor_profiles`

| 字段 | 说明 |
|---|---|
| `id`, `tenant_id` | 租户归属 |
| `name`, `brand_key`, `canonical_domain`, `official_url` | 竞品/品牌身份 |
| `category`, `brands_json`, `models_json` | 类别、品牌别名和型号 |
| `target_countries_json` | 本雷达关注市场 |
| `status` | `draft/active/paused/archived` |
| `scan_frequency_days` | 单人版默认 7 天，最短 1 天 |
| `last_scanned_at`, `next_scan_at` | 调度信息 |
| `created_by`, timestamps | 审计 |

唯一约束：`(tenant_id, canonical_domain, brand_key)`，允许同一集团官网下存在多个独立品牌，但不
允许重复添加同一品牌。平台、社交、搜索和新闻域名不能创建为竞品档案。

#### `competitor_network_edges`

该表描述“谁与哪个竞品有什么关系”，而不是把关系塞进 Lead notes：

| 字段 | 说明 |
|---|---|
| `id`, `tenant_id`, `competitor_id` | 归属 |
| `subject_domain`, `subject_name`, `country` | 经销商或组织实体 |
| `relation_type` | `official_distributor/sells_brand/imports_brand/services_brand/mentions_model` |
| `status` | `observed/verified/contradicted/inactive` |
| `first_seen_at`, `last_seen_at` | 首次和最近证据 |
| `confidence_score` | 规则分，不是模型 confidence |
| `candidate_id`, `lead_id` | 转化关联 |

一个关系至少关联一条 `candidate_evidence`；关系本身不重复保存长文本。
建议唯一约束：`(tenant_id, competitor_id, subject_domain, relation_type)`。

#### `radar_snapshots`

每次成功扫描保存可比较的规范化快照：

- 竞品事实版本；
- 排序后的关系稳定键集合；
- 来源 URL 和内容 hash；
- 扫描策略/Provider/model/prompt 版本；
- 成功、部分成功和失败来源列表；
- 调用次数、tokens 和成本。

快照只保存结构化结果和必要证据，不保存无限量原始 HTML。

#### `radar_events`

| 事件类型 | 说明 |
|---|---|
| `distributor_added` | 出现新的已验证经销关系 |
| `distributor_removed` | 连续确认后关系消失 |
| `country_entered` | 发现竞品进入新的目标国家 |
| `model_launched` | 官网出现新的相关型号 |
| `contact_changed` | 公开业务联系路径变化 |
| `price_signal_changed` | 同一公开型号、币种和计价单位下出现可比价格变化 |
| `relation_strengthened` | 从普通在售升级为官方经销等更强证据 |
| `source_unavailable` | 来源不可达，只是运维事件，不等于经销商被移除 |

状态为 `new/acknowledged/converted/dismissed`。事件可转 Candidate，但事件本身不是 Lead。
价格信号只用于内部市场判断，缺少同型号、币种、单位或日期时不得生成价格变化事件，也不得进入
外联事实库。

### 16.7 扫描、diff 与误报控制

1. 每个来源独立执行并返回部分成功；
2. 只有至少一个关键来源成功，才生成业务 diff；
3. 域名、Provider ID 和官方地址用于实体合并；
4. 新关系可以立即产生 `distributor_added`，但仍进入人工审核；
5. 关系移除必须满足以下任一条件：
   - 官方页面明确不再列出且页面结构仍有效；
   - 连续两次完整扫描未发现，间隔达到 watch rule；
   - 用户人工确认；
6. 单次超时、403、页面空白或搜索无结果只能产生 `source_unavailable`；
7. 内容 hash 变化先触发局部重抽取，不能只凭整个页面 hash 宣布业务变化；
8. 同一变化在同一快照周期只产生一个幂等事件；
9. 只有经销关系新增/加强等机会事件能自动建议 Candidate，型号和价格事件只进入情报流。

### 16.8 经销商机会评分

先应用通用 Candidate 硬门禁，再增加雷达维度：

| 维度 | 权重 |
|---|---:|
| 官方经销/经销商官网的品牌证据 | 30 |
| 产品类别与驰象匹配 | 20 |
| 目标国家与地域覆盖 | 15 |
| 跨竞品代理数量 | 15 |
| 公开业务联系路径 | 10 |
| 最近 180 天的证据时效 | 10 |

跨竞品代理是“渠道能力强”的信号，不等于“愿意更换供应商”。对竞品关系的解释要使用中性语言：
`已公开销售相关品牌，具备品类和渠道经验`，不能写成 `正在寻找替代供应商`。

### 16.9 Candidate 与外联规则

雷达发现的经销商先创建/关联 `AcquisitionCandidate`：

- `source=competitor_radar`；
- 保存竞品关系，但不把竞品名拼进普通销售备注；
- Candidate 卡可显示内部竞品上下文；
- 晋升 Lead 后保留来源 lineage；
- 外联 prompt 默认不能使用竞品品牌、不能说“我们监控了你”、不能暗示知道对方采购记录；
- 只有公开、与对方企业自身相关的事实才能用于个性化。

### 16.10 Job 与调度

```text
radar_scan
  -> competitor_site_scan
  -> reverse_dealer_search
  -> radar_dealer_verify
  -> radar_diff
  -> candidate_assessment
```

单人版不在 Flask Web 进程启动后台线程。调度方式：

1. 用户可手工“立即扫描”；
2. 系统提供 `enqueue_due_radar_scans` 应用服务/CLI；
3. 部署环境用 cron 或受控调度器定时调用；
4. 服务为到期竞品创建持久化 Job；
5. Worker 重启和重试遵守既有 Job 幂等边界。

默认每个竞品 7 天扫描一次；只有频繁变化且实际能产出 Candidate 的竞品才缩短频率。

### 16.11 UI

竞品雷达作为“获客”下的二级入口，不挤占主导航。页面包含：

- 总览：监控竞品数、新变化、新经销商候选、扫描失败和本月成本；
- 竞品卡：品牌、官网、类别、型号、目标国家、经销商数、最近扫描、下次扫描；
- 网络视图：按国家和竞品筛选经销商，标明关系类型和证据等级；
- 变化流：新增、移除、加强、不可达，支持确认和忽略；
- 竞品详情：时间线、快照 diff、来源证据和扫描日志；
- 候选动作：补充研究、转候选、接受为 Lead、拒绝并记录原因；
- 监控设置：频率、国家、来源、预算、暂停和归档。

首期使用列表、表格和分组即可；只有经销商关系足够多时再增加网络图或地图，避免为了展示而增加
复杂前端。

### 16.12 安全与访问边界

- 只监控公开企业和产品信息，不建立私人个人行为档案；
- 不登录竞品后台、经销商门户或社交账号；
- 不绕过验证码、付费墙、robots 或访问控制；
- 所有官网扫描复用 URL Fetcher 的 SSRF、大小、跳转和 Content-Type 限制；
- 模型不能根据竞品页面指令改变系统 prompt；
- 删除竞品档案默认归档，历史 Candidate/Lead/Evidence 不级联删除；
- 每个 Radar 表、Job 和查询都显式 tenant-scoped；
- `COMPETITOR_RADAR` 关闭时，页面、路由、定时入队和 Worker 都拒绝执行。

### 16.13 指标

- 每个竞品每次扫描的来源成功率和成本；
- 新发现、验证通过和人工接受的经销商数量；
- 跨竞品大经销商数量；
- 变化事件误报率；
- Radar Candidate 的联系率、积极回复率和转化率；
- 每个接受 Radar Candidate 的成本；
- 连续 90 天无有效候选的竞品，建议自动降频但不自动删除。

### 16.14 雷达验收标准

- 可手工添加或由 MiMo 建议竞品，平台/社交 URL 被拒绝；
- 能从竞品官方经销商页建立带来源的关系；
- 能用本地语言反向搜索并验证经销商官网；
- 同一经销商代理多个竞品时只保留一个企业实体和多条关系；
- 快照重跑幂等，不重复创建事件和 Candidate；
- 单个来源失败不会把全部经销商标记为移除；
- 新经销商可转入通用 Candidate 审核队列；
- Candidate 晋升 Lead 后保留竞品来源，但外联不泄露监控行为；
- 定期扫描由持久化 Job 执行，不使用 Web 进程线程；
- PostgreSQL 并发、租户隔离、Capability、SSRF 和 prompt-injection 测试通过。

## 17. 单人版 UI

不增加十几个渠道菜单，也不向经营者暴露 Mission Run、Trust Tier、Score Version、BrowserRun、
Capability 等内部术语。它们只出现在高级详情和调试视图。用户默认看到“找客户任务、正在搜索、
待审核客户、推荐理由、证据来源、需补充信息、进入客户库”。核心导航建议为：

1. **今日工作台**：唯一主入口，汇总待审核候选、待批准草稿、回复、跟进和失败任务；
2. **获客任务**：创建任务、查看阶段进度、暂停和复用；
3. **竞品雷达**：作为获客下的二级入口，展示监控、经销网络和变化机会；
4. **候选审核**：证据卡、评分、未知项、接受/拒绝；
5. **Leads/CRM**：继续使用现有客户跟进流程；
6. **外联**：草稿、dry-run、批准、发送结果；
7. **知识与 Provider**：产品事实、API 状态、预算和健康检查。

### 17.1 创建 Mission

单页表单优先，首屏只显示产品、国家和买家类型三个必填字段。默认值来自产品知识和上一次成功任务；
语言自动推导，高级 ICP、排除词、渠道和预算折叠，避免把用户变成搜索工程师。

### 17.2 今日工作台

工作台只回答“现在最值得做什么”，首屏提供真实计数与直接动作：

- `X` 个客户等待审核：继续审核；
- `Y` 个回复等待处理：查看回复；
- `Z` 个任务正在运行或验证：查看进度；
- 今天到期的跟进：进入 CRM；
- 失败、超预算或需要补证的任务：查看原因并重试；
- 创建新的找客户任务。

成本、Provider 指标和调试日志留在任务详情，不在首页堆叠。现有 `/workbench` 模板作为入口继续使用，
但必须接入真实查询和空状态，不再只是静态卡片。

### 17.3 候选卡

候选卡按三层渐进披露，避免一次展示所有审计字段：

- 第一层：公司、机会国家、一句话推荐理由、Priority/暂定状态、联系路径、接受/拒绝；
- 第二层：2–3 个关键证据、观察事实与 AI 推断、评分拆解、未知项和风险、补充研究；
- 第三层调试：claim IDs、trust tier、content hash、模型、Prompt、评分和策略版本。

批量拒绝必须选择结构化原因。批量接受只允许已通过门禁的候选，单次最多 20 个并显示确认摘要；接受
只是晋升 CRM，不触发外联。系统不提供批量首发。

### 17.4 自动化级别

单人版只需要三个清晰档位：

| 档位 | 行为 |
|---|---|
| 辅助 | AI 生成计划和草稿，用户逐步触发 |
| 推荐默认 | 自动研究与验证，用户审核候选和外发 |
| 高自动化 | 自动运行已批准 Mission，但仍不自动首发/群发 |

### 17.5 通知与移动端

首期提供应用内通知、未读角标和工作台失败提示；任务完成邮件是可选设置，未配置邮件 Provider 时不阻断
使用。浏览器 Push、短信和微信通知不进入首期。告警只说明发生了什么和下一步，不包含 API Key、完整
URL query 或联系人敏感内容。

移动端目标是“可审核”，不是完整后台管理：支持工作台、候选第一/第二层、接受、拒绝、补证、拨号和
打开公开 WhatsApp 链接。Mission 高级设置、证据并排比较、站点策略和调试信息以桌面端为主。

WhatsApp 首期只把明确公开的企业号码规范化为 E.164 并打开 `wa.me`，不自动发送。CSV 导出作为低成本
增强，默认只导出业务字段和来源，不导出内部调试字段；导出动作 tenant-scoped 且写审计日志。

## 18. 安全与合规边界

### 18.1 外部网页是不可信输入

所有网页内容进入模型前必须：

- 明确包在“untrusted evidence”边界；
- 删除脚本、样式、隐藏文本和危险链接；
- 限制单页大小、总字符数和跳转次数；
- 不允许网页要求模型调用工具、泄露 prompt 或更改产品事实；
- 结构化输出后再由业务 Schema 和 URL 校验器检查。

### 18.2 URL Fetcher 防护

- 只允许 HTTP/HTTPS；
- 拒绝 localhost、私网、链路本地、云 metadata 和非常规端口；
- DNS 解析前后检查，防止重绑定；
- 限制重定向、响应大小、Content-Type 和超时；
- 不携带登录 Cookie；
- 日志不保存 API Key、Authorization 或完整敏感响应；
- 浏览器回退运行在隔离 Worker，不与主 Web 进程共享权限。

### 18.3 API Key

- 使用现有加密 SecretStore；
- UI 只显示掩码和最后验证时间；
- Job payload 只传 provider 配置引用，不传明文 Key；
- Provider 错误对用户显示安全摘要，完整错误只在受控服务端日志；
- 未来公共 SaaS 再增加每租户 Provider 权限和用量配额。

### 18.4 外联

- 保留退订、抑制、每日限额、测试 allowlist 和审计；
- 不因“只有一个人使用”而取消发送安全；
- 联系人的合法使用基础和地区规则需要由经营者确认；
- 角色邮箱与个人邮箱分开标记；
- 不把 SMTP 探测的临时响应当成绝对有效证明；
- 对退订、投诉和硬退信立即进入 suppression。

## 19. 故障、成本与可观测性

### 19.1 统一错误分类

```text
auth_error
quota_exceeded
rate_limited
provider_timeout
provider_unavailable
invalid_response
schema_violation
policy_blocked
source_unreachable
source_stale
no_results
partial_success
```

只有 `rate_limited/provider_timeout/provider_unavailable` 等明确临时错误自动指数退避；
认证、策略和 Schema 错误不盲目重试。

### 19.2 默认预算

单人版建议初始默认值：

- 每个 Mission 最多 5 个 AI 搜索动作；
- 最多发现 30 个原始候选；
- 最多深入验证 10 个候选；
- 每天最多 10 次 YouTube `search.list`；
- 每次官网最多抓 5 页；
- 单页正文上限 200 KB，超出截断；
- 草稿只对人工接受的 Lead 生成；
- 达到任一上限后暂停并展示部分结果，不自动扩容。

这些不是 SaaS 套餐，而是保护费用和时间的内部安全上限。

### 19.3 指标

每个 Provider 和渠道记录：

- 请求成功率、P50/P95 延迟、超时和限流率；
- 搜索次数、页面数、tokens 和可用费用；
- 原始候选数、去重后数、硬门禁通过数；
- 人工接受率；
- 取得可联系路径比例；
- 发送率、回复率、积极回复率、退订和退信；
- 每个接受候选成本、每个积极回复成本；
- 草稿事实越界数，目标必须为 0。

“每天抓到 1000 条”不作为成功指标。

### 19.4 单人版部署拓扑

开发环境使用 Windows + Docker Desktop/WSL2；需要持续自动运行时沿用现有阿里云 ECS + Docker
Compose 方案。首期不为了部署方便迁移到新 PaaS，也不引入 Kubernetes。运行单元为：

```text
web
redis
database
default-worker      # 规划、静态获取、抽取、评分、晋升、草稿
browser-worker      # 独立 browser 队列，并发 1，可关闭
scheduler/reconciler
```

Web 和普通 Worker 镜像不安装浏览器；Browser Worker 使用独立镜像，固定 Node、Playwright MCP 和
Chromium 版本。SQLite 只允许单写入 Worker；需要多个 Worker 或持续并发任务前必须迁移 PostgreSQL。
现有 2 vCPU/4 GB 规格可用于不启用浏览器的起步环境；启用浏览器后必须观察峰值内存，发生 OOM 或队列
持续堆积时优先升级资源，不通过提高并发掩盖问题。

### 19.5 日志与运行追踪

首期不部署 ELK。所有服务向 stdout 输出结构化 JSON，至少包含 `request_id`、`job_id`、`mission_id`、
`browser_run_id`、`provider`、`stage`、`error_code`、`duration_ms` 和安全的 tenant 标识。不得记录 Key、
Authorization、Cookie、完整第三方响应或模型隐藏推理。Docker 配置日志轮转；任务详情从持久化 Job、
BrowserRun 和 AuditEvent 展示业务时间线，数据库不作为无限增长的原始日志仓库。Sentry 可作为后续可选
错误聚合，不是首期依赖。

### 19.6 备份与保留

沿用现有数据库备份/恢复 Runbook，并增加获客数据边界：

- Candidate、Evidence 元数据、URL、excerpt、hash、Assessment、决策和 Mission 结果保存在数据库；
- 截图与文本快照写入专用持久化 volume 或对象存储，不写临时 `.runtime` 目录；
- 截图和临时快照默认保留 30 天，到期由可审计清理 Job 删除；被人工标记为关键证据的制品可延长；
- 删除制品不删除 Evidence 元数据、URL、hash 和审核历史；
- 单人版初始目标 RPO 24 小时、RTO 4 小时，每日备份并定期执行恢复演练；
- Redis 仍是临时队列状态，不作为唯一业务真相。

### 19.7 初始性能目标

以下是首期验收与调优目标，不是公共 SaaS SLA：

| 场景 | 初始目标 |
|---|---|
| 创建 Mission 并入队 | < 1 秒 |
| 首次显示任务进度 | < 5 秒 |
| 单国家获得 10 个可审核候选 | 中位数 <= 5 分钟，P95 <= 15 分钟 |
| 正常单人负载队列等待 | <= 60 秒 |
| 取消任务生效 | <= 30 秒 |
| BrowserRun | 硬上限 120 秒，达到预算保留部分结果 |
| 工作台/候选列表 | staging P95 < 1 秒，不含后台研究 |

指标按 `source_channel` 和是否使用浏览器分组，防止动态页面拖慢后被平均数掩盖。真实样本不足前这些值是
校准目标；若连续不达标，应先减少页面预算和动态浏览器使用，再考虑扩容。

### 19.8 健康检查、通知与告警

`live` 只证明进程存活；`ready` 检查数据库、Redis 和必要队列。MiMo 健康不能在每次探针中发起付费
请求，而应展示最近一次安全验证、最近成功和连续失败数；Browser Worker 用心跳和已安装版本上报状态。

首期告警条件：MiMo 认证/额度错误立即告警，或连续失败 3 次；最老队列等待超过 5 分钟；Browser
Worker 超过 2 分钟无心跳；BrowserRun 超预算或失联；近一小时 Job 失败率超过 20%；磁盘使用超过
80%；最近成功备份超过 26 小时。默认进入应用内通知，可选发邮件；同一根因做时间窗去重，恢复后生成
恢复事件。

### 19.9 Browser Worker 清理与网络边界

每个 BrowserRun 使用独立临时目录和上下文，并在 `finally` 中依次关闭页面、context、MCP 子进程和
浏览器；软终止超时后必须强制结束整个进程组。Worker 启动和周期 reconciler 清理失联进程、过期 lease
与临时目录。容器启用 init、内存/CPU/进程数限制和自动重启。

应用层在连接前验证 URL/DNS，并在每次 redirect 和最终 URL 后重新验证；浏览器容器还必须在网络层
阻断 localhost、私网、链路本地和云 metadata，因为仅靠两次 DNS 查询不能彻底防止重绑定。浏览器不
访问数据库、SecretStore、主机 Docker socket 或内部服务，只通过受限任务输入和结果目录通信。

## 20. 测试与验收策略

### 20.1 单元与契约测试

- 每个 Provider 使用录制/手写的安全 fixture，不依赖真实联网；
- JSON Schema、错误映射、配额和部分成功；
- URL 规范化、SSRF、域名去重、国家和排除项；
- `country_unknown/conflicting` 进入补证，人工 override 可审计并触发重新评估；
- ScoreInput 未知值、覆盖率、暂定 Priority 和相同输入确定性；
- Candidate 状态机和非法转换；
- Candidate 晋升 Lead 的幂等；
- 所有 Repository 的跨租户读写拒绝；
- 产品事实 ID 校验和禁止声明检测；
- YouTube 评论只生成 signal，不直接生成已验证联系人。
- 雷达关系类型、连续移除确认、跨竞品实体合并和事件幂等。
- 反馈阈值只生成建议，应用建议创建新版本且重复操作幂等。

### 20.2 集成测试

- Job/RQ 只传 `job_id`；
- Worker 重试不重复 Candidate/Evidence/Lead；
- 周期 reconciler 能恢复失联 Job，并把 Mission/BrowserRun 收敛到正确终态；
- Provider auth/quota/timeout 的安全失败；
- MiMo/Browser 故障时静态 Fetcher 与人工补证路径仍可使用；
- Browser 子进程在成功、失败、取消、超时和 Worker 崩溃场景下均被回收；
- migration 从 0012 升级、降一级、再升级；
- PostgreSQL 上的唯一约束和并发晋升；
- Capability 关闭时路由和 Worker 都拒绝执行。
- 到期竞品通过外部调度创建持久化 Job，Web 进程不启动扫描线程。

### 20.3 AI 评估

- 固定 benchmark，不能每次临时挑好看的例子；
- 结构化输出成功率目标 >= 98%；
- 外发禁止事实命中率必须 0；
- 首期候选精确率目标 >= 70%，之后根据真实样本提高；
- 引用 URL 可访问率和引用支持度分别检查；
- 每次 prompt/model 升级先离线对比，再做有限 live smoke。

### 20.4 端到端验收

1. 创建“秘鲁摩托车发动机经销商”Mission；
2. MiMo 生成西语查询计划；
3. 保存企业候选和引用；
4. 纯电企业被硬规则拒绝或标为证据不足；
5. 合格企业展示官网产品和联系证据；
6. 用户接受后幂等晋升 Lead；
7. 草稿只使用批准产品事实；
8. 未批准前无真实外发；
9. 发送后进入现有 Outreach/Activity；
10. 回复被分类并进入今日工作台。

## 21. 实施阶段

### Phase 0：前置一致性

- 新建 migration 修复 `AdminUser.auth_version`；
- 合并/确认 INT-004 ADR 基础；
- 在 PostgreSQL 执行 migration smoke；
- 保持现有 286 个测试通过；
- 决定并登记新 Capability 名称。

### Phase 1A：不依赖浏览器的最小可靠闭环

- Product Knowledge Snapshot；
- MiMo Provider、结构化 Schema 和健康检查；
- Acquisition Mission、Candidate、Evidence；
- 手工 URL + MiMo Web Discovery；
- 官网受限 Fetcher；
- 国家未知补证、缺失信号安全评分、分层证据 UI 和候选审核；
- Candidate 幂等晋升 Lead；
- 事实受限外联草稿；
- 三字段创建任务、真实今日工作台和应用内通知；
- 结构化拒绝原因、任务成本、复盘和“建议后人工应用”的反馈闭环；
- 为竞品雷达预留 `source=competitor_radar`、Evidence lineage 和 Candidate 转换契约；
- 不新增真实自动发送。

这是最重要的一期。完成后即使 Browser/MCP 不可用，用户也能从产品事实到合格 Lead 和安全草稿走完
一条路径。

### Phase 1B：受控浏览器与实用增强

- 独立 Browser Worker、`browser` 队列、进程清理、心跳和网络隔离；
- 仅在静态 Fetcher 无法读取且 SitePolicy 允许时回退 Browser MCP；
- 最小竞品入口：用户提供竞品/官方经销商 URL，复用通用 Evidence/Candidate 流程，不做定时 diff；
- 可选任务完成邮件、CSV 业务字段导出和公开企业 WhatsApp 一键打开；
- Browser 故障、禁用或未安装时 Phase 1A 全部功能保持可用。

### Phase 2：竞品雷达与稳定渠道扩展

- 正式竞品雷达：竞品档案、官网经销商、反向搜索、关系网络、快照和 diff；
- Radar Candidate 转换、变化工作台和外部定时入队；
- Google Places Text Search；
- YouTube Data API 信号；
- 官网 Contact/About 增强；
- Provider 成本/健康面板；
- Mission 复用与手动定时运行。

### Phase 3：付费数据按 ROI 接入

- 先 Hunter，再根据覆盖率决定 Apollo；
- 用 50–100 家真实目标企业做付费 Provider 对比；
- 只有“每个接受 Lead 成本/回复率”优于现有流程才保留；
- 贸易数据先做市场分析，再评估公司级供应商。

### Phase 4：反馈建议增强

- 跨任务接受/拒绝原因和结果趋势；
- 按国家和买家类型提出查询模板调整建议；
- 回复分类与下一步建议；
- 在高置信、已批准 Mission 上自动定期研究；
- 仍由用户批准策略版本变化，并保留首次/批量外发门禁。

### Phase 5：未来公共 SaaS

只有触发商业化评审后再做：

- 每租户 Provider 凭据、额度和计费；
- 计划/权限 Entitlement；
- 多用户审批、角色和审计导出；
- 公共注册、支付、合规和 SLA；
- Provider 数据处理协议和地区化策略。

## 22. 分阶段 Definition of Done

### 22.1 Phase 1A

- 一个用户能创建、运行、暂停和查看 Mission；
- 创建首屏只有产品、国家、买家类型三个必填字段，高级设置默认折叠；
- 今日工作台显示真实待审核、运行中、失败、回复和跟进计数及直接动作；
- MiMo 搜索结果包含可点击证据，而不是只有模型总结；
- 没有邮箱的公司候选不会被静默丢弃；
- 纯电、供应商、平台页和地区不符有确定性拒绝原因，国家未知/冲突进入补证而非被丢弃；
- Candidate/Evidence/Job/Lead 全部 tenant-scoped；
- 同一任务重试不会重复创建 Candidate 或 Lead；
- AI 不能直接接受候选、写 CRM 或发送邮件；
- 草稿的每项产品声明能映射到批准事实 ID；
- 未批准价格、MOQ、交期、认证和质保不会出现在外发内容；
- Provider Key 不进入 Job payload、日志或数据库明文字段；
- URL Fetcher 通过 SSRF、大小、重定向和 Content-Type 测试；
- 相同持久化 ScoreInput 得到相同评分，未知 Intent 不显示为低意向；
- MiMo 不可用时静态/人工降级路径仍可完成审核和 CRM 晋升；
- 反馈只生成可解释建议，未经用户确认不改变排除词或评分权重；
- 任务成本、结构化拒绝原因、应用内通知和初始性能指标可查看；
- 数据库恢复演练包含 Candidate/Evidence；
- 真实联网测试是显式 opt-in，默认测试套件完全离线；
- PostgreSQL migration smoke、ruff、format 和 pytest 通过；
- 至少用 30 个真实正负样本形成首版渠道/模型基准报告；
- 竞品雷达共享基础契约已固定，Phase 2 无需另建 Lead、Evidence 或 Job 系统。

### 22.2 Phase 1B

- Browser Worker 禁用、未安装或故障时 Phase 1A 行为和数据保持不变；
- 动态浏览器只在静态 Fetcher 失败且 SitePolicy 允许时运行；
- Browser Worker 并发、超时、进程组清理、心跳、失联恢复和网络阻断通过测试；
- 截图制品使用持久化目录，30 天保留与审计清理策略可执行；
- 最小竞品 URL 能复用 Evidence/Candidate 审核链路，不建立第二套 Lead 系统；
- 可选邮件、CSV 导出和 WhatsApp 链接不绕过外发与审计边界；
- 关键 Browser MCP 端到端流程通过。

## 23. 最终产品意见

单人版先做好再升级 SaaS 是正确方向，但“单人版”不等于“把所有东西自动化”。最值得自动化的是
重复研究、证据整理、语言转换和草稿，不是事实判断与高风险外发。

对当前业务，可靠获客组合应是：

```text
MiMo 多语言搜索
  + 企业官网验证
  + 竞品雷达的经销网络与变化机会
  + Google Places 本地商业发现
  + YouTube 市场/意向信号
  + Hunter/Apollo 按需增强
  + 人工审核与反馈
```

而不是：

```text
二十个脆弱爬虫
  + 一个全权 Agent
  + 自动群发
```

渠道会继续增加，但每个新渠道必须先回答三个问题：

1. 它提供市场、企业、意向、联系还是触达中的哪一种数据？
2. 是否有官方/授权的稳定访问方式和可保存证据？
3. 它是否提高了接受率、联系率或积极回复率，而不只是增加条数？

答不清这三个问题的渠道，不进入生产主流程。

## 24. 外部调研依据

- [YouTube Data API Overview](https://developers.google.com/youtube/v3/getting-started)
- [YouTube `search.list`](https://developers.google.com/youtube/v3/docs/search/list)
- [YouTube `commentThreads.list`](https://developers.google.com/youtube/v3/docs/commentThreads/list)
- [YouTube API Services Terms](https://developers.google.com/youtube/terms/api-services-terms-of-service)
- [Google Places Text Search](https://developers.google.com/maps/documentation/places/web-service/text-search)
- [Hunter API](https://hunter.io/api-documentation)
- [Apollo People API Search](https://docs.apollo.io/reference/people-api-search)
- [TikTok Research API](https://developers.tiktok.com/products/research-api/)
- [LinkedIn API Documentation](https://learn.microsoft.com/en-us/linkedin/)
- [WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api/)
- [UN Comtrade API](https://comtradeapi.un.org/)
- [OpenAI API Web Search example](https://platform.openai.com/docs/quickstart/make-your-first-api-request)
- [Gemini Grounding with Google Search](https://ai.google.dev/gemini-api/docs/google-search)
- [Claude Web Search Tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool)
- [Perplexity Search API](https://docs.perplexity.ai/docs/search/quickstart)
- [Scrapy GitHub](https://github.com/scrapy/scrapy)
- [Crawl4AI GitHub](https://github.com/unclecode/crawl4ai)
- [Firecrawl GitHub](https://github.com/firecrawl/firecrawl)
- [SearXNG GitHub](https://github.com/searxng/searxng)
- [Google API Python Client](https://github.com/googleapis/google-api-python-client)
- [MiMo 官方文档](https://mimo.mi.com/docs)
- [MiMo Claw MCP 工具调用说明](https://mimo.mi.com/docs/en-US/news/latest/mimoclaw)
- [Microsoft Playwright MCP](https://github.com/microsoft/playwright-mcp)
- [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [LinkedIn 禁用软件和自动化规则](https://www.linkedin.com/help/linkedin/answer/a1341387/prohibited-software-and-extensions?lang=en)
- [LinkedIn User Agreement](https://www.linkedin.com/legal/user-agreement)

## 25. 已确认的实施范围

本设计已经完整包含竞品雷达、YouTube、Places、Hunter、Apollo 和后续多模型边界；完整设计不
等于一次性实施。建议第一批批准 **Phase 0 + Phase 1A**，先证明“MiMo + 官网证据 + 候选审核 +
安全草稿”能产生合格 Lead；随后按 Phase 2 实现正式竞品雷达、YouTube 和 Places，再按指标增加
付费渠道。

用户已于 2026-08-01 确认：

- 先完成单人版，保留未来公共 SaaS 的 `tenant_id`、Capability、Job 和审计边界；
- 增加正式国家/ICP 筛选与可解释客户评分；
- 使用 MiMo 作为首期规划、研究、抽取和草稿模型；
- 允许通过受控 MCP 浏览器研究公开且允许自动访问的网站；
- LinkedIn 固定为人工或官方数据通道，不做浏览器自动抓取；
- 不改掉已经设计完成的竞品雷达、YouTube、Places、Hunter、Apollo 和 Outreach 续接位置。

第一实施批次为 **Phase 0 + Phase 1A + 国家/评分的最小可靠闭环**，必须在不安装或停用 Browser MCP
时独立可用。受控 Browser MCP 和最小竞品入口属于 Phase 1B 增强；完整竞品雷达和更多渠道仍按后续
阶段接入，不能与首批安全核心混为一次大提交。

## 26. 国家、ICP 与评分补充设计（已确认）

### 26.1 国家是任务约束，不是备注

Mission 使用 ISO 3166-1 alpha-2 国家代码。用户可以选择多个国家，但执行计划必须拆成单国 run，
每个 run 独立使用当地语言、搜索词、排除词、渠道和预算。

Candidate 分开保存：

- `hq_country_code`：总部或注册地；
- `opportunity_country_code`：本次销售机会所在市场，也是硬门禁字段；
- `contact_country_code`：联系人所在国家，只用于语言、时区和联系安排；
- `country_resolution_status`：`unknown/confirmed/conflicting`。

确认机会国家至少需要一个 A 级来源，或两个相互独立且一致的 B/C 级来源。信息不足或来源冲突时不
允许进入推荐队列，但 Candidate 保留在“待确认国家”补证队列，不能让模型根据域名后缀或语言猜测
国家。用户可以用公开来源和结构化理由人工确认；该记录是单独的审计 override，不伪装成 A/B 级证据，
确认后重新运行门禁和评分。

### 26.2 ICP 输入

首期 Target Profile 在数据层可以包含完整 ICP，但创建界面只有以下三个必填输入：

- 已批准产品；
- 目标国家；
- 买家类型，例如进口商、经销商、批发商、维修网络。

语言自动推导；行业、公司规模、必须包含词、排除词/排除业务以及候选、页数、token 和时间预算都属于
高级设置并有安全默认值。

### 26.3 先硬门禁，后评分

硬拒绝原因使用机器可统计 code：`wrong_country`、`wrong_buyer_type`、`excluded_business`、
`no_independent_identity`、`insufficient_product_evidence`、`no_contact_path`、`duplicate`、`suppressed`、
`policy_blocked`、`stale_source`。`country_unknown` 与 `country_conflicting` 是补证原因，不是拒绝原因。

通过门禁后使用 `score-v1`：

```text
Fit = 产品相关 35% + 买家角色 25% + 国家匹配 20% + 公司规模 10% + 行业匹配 10%

Intent = 直接购买信号 40% + 近期活动 25% + 竞品/经销信号 20% + 信号时效 15%

DataQuality = 身份质量 25% + 来源可信度 25% + 可联系性 20%
              + 独立证据 15% + 数据时效 15%

Priority = round(0.50 * Fit + 0.30 * Intent + 0.20 * DataQuality)
```

等级为 `S >= 85`、`A >= 70`、`B >= 55`、`C < 55`。未知输入使用 `None` 并按已知权重重新归一化，
同时显示 `signal_coverage`；Intent 全未知时显示“暂无意向信号”，Priority 标记为暂定。覆盖不足 60%
时最高不能为 S。模型 `ai_confidence` 单独展示，不参与硬门禁，也不能替代来源质量。每次 Assessment
保存 evidence bundle hash、score/policy/prompt/model 版本、完整 ScoreInput、分项、claim IDs 和解释。

### 26.4 CRM 筛选

Lead 列表增加国家、最低/最高 Priority、等级、来源、是否可联系和证据状态筛选；默认提供 S/A 优先、
目标国家、待审核、缺联系路径四个快捷视图。晋升 Lead 时复制 Candidate 的国家和评分快照，同时保留
原 Assessment，保证历史可解释。

## 27. MiMo + 受控 Browser MCP 补充设计（已确认）

### 27.1 角色分工

MiMo API Key 不直接连接浏览器。默认先由受限 HTTP Fetcher 获取静态公开页面；只有静态页面无法满足
证据需求且站点策略允许时才创建 BrowserRun。LeadFlow 是 MCP Host 和唯一控制面：MiMo 返回结构化
计划或高层工具调用，LeadFlow 先检查 Capability、站点策略、URL/SSRF、预算和动作，再通过 MCP
Client 调用隔离的 Playwright MCP Server。

浏览器只负责读取页面；Candidate/Evidence、国家解析、门禁、评分、审核和 Lead 晋升仍由确定性业务
服务完成。MiMo 不获得数据库 Session、Repository、发送服务或原始 MCP 工具列表。

### 27.2 浏览器选择

自动研究使用独立、无登录、无持久 Cookie 的 Playwright MCP 浏览器，不连接用户日常 Chrome。
Chrome DevTools MCP 仅用于工程调试，因为它能查看和修改连接浏览器中的内容，不适合作为生产获客
边界。MCP 官方工具的 allowlist 只能作为纵深防御，LeadFlow 仍须自行实施安全控制。

Playwright MCP 运行在独立 `browser-worker` 镜像和 `browser` 队列，首期全局并发 1；Web 与普通
Worker 不安装或启动浏览器。Browser Worker 缺失、禁用或故障时返回可识别的降级结果，不影响静态
Fetcher、人工补证、审核和 CRM 晋升。

### 27.3 网站访问分级

| 模式 | 行为 |
|---|---|
| `auto_public` | 企业官网、政府/协会公开名录在策略和 robots 允许时有限只读研究 |
| `review_required` | 未知目录由用户先批准域名策略 |
| `manual_only` | 登录或条款不明确的平台只允许人工录入 |
| `blocked` | LinkedIn 等明确限制当前用途的平台在浏览器启动前硬阻断 |

LinkedIn 的系统 block 高于租户数据库策略，不能通过普通设置覆盖。系统不实现验证码绕过、代理轮换、
指纹伪装、Cookie 复制、隐藏接口、批量资料遍历、自动加好友或自动私信。

### 27.4 高层工具和预算

MiMo 只看到 `open_allowed_url`、`read_current_public_page`、`follow_same_site_link`、
`capture_evidence`、`stop_research`。业务 Agent 不注册任意代码执行、页面 evaluate、输入、表单、上传、
下载、Cookie、Storage 或网络正文工具。

默认每次 BrowserRun：最多 10 页、120 秒、5 MB 文本快照、12 次工具调用；同域并发 1，动作间隔至少
3 秒。captcha、登录墙、策略拒绝、提示注入或最终 URL 越界时关闭会话且不自动重试。

### 27.5 证据与失败

每条 Evidence 保存来源 URL、title、限长 excerpt、trust tier、retrieved/observed time、content hash、
支持的 claim、validation status 和可选截图 hash；不保存整页 HTML、Cookie 或完整第三方响应。

截图和临时文本快照存入专用持久化制品目录，默认保留 30 天，由可审计清理任务删除；Evidence 元数据、
URL、excerpt 和 hash 不随截图到期删除。BrowserRun 无论成功、失败、取消或超时都必须清理 context、
子进程、进程组、lease 和临时目录，周期 reconciler 负责处理 Worker 崩溃后的遗留项。

浏览器错误统一为策略、URL、页面、预算、Provider、MCP 和内容七类。错误摘要不得包含 API Key、URL
query、Cookie、表单正文、模型 reasoning 或联系人私密内容。

## 28. 可执行实施计划

逐文件、逐 migration、逐测试、逐提交的正式计划位于：

`docs/superpowers/plans/2026-08-01-mimo-mcp-country-scoring-acquisition.md`

现有计划是在本次单人版收敛审查前生成，必须在本设计获得书面复核后同步调整：先交付不依赖浏览器的
Phase 1A，再交付 Browser Worker 与最小竞品入口 Phase 1B；同时补入工作台、通知、反馈、降级、日志、
备份、性能和恢复任务。计划同步完成前不得直接按旧任务顺序实施功能代码。
