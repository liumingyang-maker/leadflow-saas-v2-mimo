# LeadFlow SaaS V2 自动开发总控包

这套包用于把 **Codex（架构、计划、审核、发布）** 与 **Reasonix/DeepSeek（编码、测试、返工）** 组合成一个可追踪、可恢复、可审计的自动开发流水线。

## 你只需要做三件事

1. 将本目录复制到新仓库 `leadflow-saas-v2` 的根目录。
2. 在 `config/autopilot.json` 中填写 Reasonix MCP 工具名称，或保留默认 `reasonix`。
3. 在 Codex 中打开新仓库，把 `MASTER_AUTOPILOT_PROMPT.md` 整段发给 Codex。

之后 Codex 必须：

- 读取 `AGENTS.md`
- 使用本地 skills
- 生成任务卡
- 将实现工作交给 Reasonix/DeepSeek
- 自己只做架构、审查、验收和发布
- 每个任务自动测试、返工、PR、CI、合并
- 遇到真正产品歧义时一次性提问

## 不建议使用 YOLO

默认采用 Codex workspace-write + auto review，而不是绕过沙箱。自动化并不等于无边界权限。

## 首次启动

```powershell
Copy-Item config\autopilot.example.json config\autopilot.json
python tools\autopilot.py init
python tools\autopilot.py status
python tools\install_ui_skills.py --yes
python tools\autopilot.py prepare
```

如果使用 Codex CLI：

```powershell
python tools\autopilot.py codex
```

## 安全边界

自动化允许编辑新仓库、运行测试、建分支、提交、推送、PR、CI、合并。

自动化禁止修改旧仓库、删除真实数据、打印真实密钥、生产部署、强制推送、绕过测试，以及把全部编码任务压给 Codex。
