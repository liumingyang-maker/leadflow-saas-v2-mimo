# Automation Workflow

## 状态机

```text
READY -> PLANNING -> WORKER_BUILD -> VERIFYING -> REVIEWING
      -> WORKER_FIX (循环) -> ACCEPTED -> PR_OPEN -> CI -> MERGED -> DONE
```

状态保存在 `.autopilot/state.json`。

## 证据目录

```text
.autopilot/
  packets/
  plans/
  logs/
  reviews/
  screenshots/
  evidence/
```

## 四轮审查

### Architecture

依赖方向、模块边界、租户隔离、事务、迁移、可扩展性。

### Security

auth/session、CSRF、输入、secrets、tenant scope、redirect、jobs、rate limit、error leakage。

### UI

design system、组件复用、响应式、a11y、动效克制、状态完整。

### Release

clean diff、tests、migrations、CI、无 secrets、PR scope。
