# LeadFlow V2 UI System — Signal Workspace

## 设计方向

现代、克制、可信的 B2B intelligence workspace。避免“AI 自动生成网站”的通用视觉。

## 色彩

- Canvas `#F5F7FA`
- Surface `#FFFFFF`
- Elevated `#F9FBFD`
- Text strong `#152033`
- Text muted `#637083`
- Border `#DCE3EA`
- Primary cobalt `#246BFD`
- Signal cyan `#00A8C6`
- Success `#168A5B`
- Warning `#D97706`
- Danger `#C83B48`
- Info background `#EAF2FF`

禁止默认紫色 AI 渐变。暗色模式留到 V2-06。

## 字体与密度

Inter 或系统 sans；数据使用 tabular numerals；正文不小于 14px；行高 1.45–1.6。

## 组件

- AppShell
- PageHeader
- KPIStat
- FilterBar
- SearchField
- DataTable
- LeadCard
- StageBadge
- ConfidenceBadge
- EmptyState
- InlineNotice
- Toast
- ConfirmDialog
- DetailDrawer
- ActivityTimeline
- ImportWizard
- JobProgress
- IntegrationCard
- SecretField
- FormSection
- CommandPalette

每个组件必须具备 default/loading/empty/error/disabled/focus 状态。

## 页面模式

### Dashboard

可行动 KPI、当前任务、待审核线索、到期跟进、最近 Inbound。

### Lead Review

高密度但清晰的列表、粘性筛选、键盘操作、右侧详情抽屉、明确接受/拒绝/补充动作。

### CRM

表格为主、保存筛选、抽屉时间线、仅选择后出现批量操作。

### Collection

来源卡片、搜索目标、地区/行业、启动前预估、启动后持久进度。

## 动效

动效性格：克制、快速、专业。

- hover/focus 100–140ms
- button/state 120–180ms
- drawer/modal 180–240ms
- page reveal 180–260ms
- 优先 opacity/transform
- 不用无意义 layout animation
- 不用无限装饰动画
- 遵守 `prefers-reduced-motion`
- loading 显示进度或 skeleton

## 可访问性

目标 WCAG 2.2 AA：可见 focus、全键盘、语义标题、完整 label、错误与字段关联、状态不只靠颜色、40x40 触控目标、reduced motion、icon button 有 accessible name。

## UI 验收

每个改动页面必须有桌面/移动截图、键盘检查、focus 检查、empty/loading/error、reduced-motion、console 无错误、无横向溢出。
