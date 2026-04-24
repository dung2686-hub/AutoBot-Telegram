# Antigravity Kit Architecture

> **Version 6.0** - Comprehensive AI Agent Capability Expansion Toolkit
> Upgraded with ECC (Everything Claude Code) best practices integration.

---

## 🚨 PROJECT-SPECIFIC CONTEXT (AutoBot-Telegram)

> [!IMPORTANT]
> **MANDATORY at session start:** Before any implementation work on this project, READ the following docs to understand current plans and progress:

| File | Content |
|------|---------|
| `docs/IMPLEMENTATION_PLAN.md` | Chi tiết plan 3 tính năng: Smart Notifications, Coupon System, Dashboard Nâng Cao |
| `docs/FEATURE_UPGRADE_SUGGESTIONS.md` | 12 gợi ý nâng cấp chia 4 tier + roadmap đề xuất |
| `docs/PLAN-restock-broadcast.md` | Plan hệ thống thông báo hàng về (Restock Broadcast) |

**Project type:** Python Telegram Bot (python-telegram-bot + SQLite + Canboso API + SePay webhook)

---

## 📋 Overview

Antigravity Kit is a modular, portable system consisting of:
- **23 Specialist Agents** - Role-based AI personas
- **50 Skills** - Domain-specific knowledge modules
- **15 Workflows** - Slash command procedures
- **Structured Rules** - By language (common, python, web)

**Portable**: Copy `.agent/` into any project to get full AI development capabilities.

---

## 🏗️ Directory Structure

```
.agent/
├── ARCHITECTURE.md          # This file
├── agents/                  # 23 Specialist Agents
├── skills/                  # 50 Skills
├── workflows/               # 15 Slash Commands
├── rules/                   # Structured Rules
│   ├── GEMINI.md            # Master config
│   ├── common/              # Language-agnostic
│   │   ├── coding-style.md
│   │   ├── git-workflow.md
│   │   ├── security.md
│   │   └── testing.md
│   ├── python/              # Python-specific
│   │   └── style.md
│   └── web/                 # Web (JS/TS) specific
│       └── style.md
└── .shared/                 # Shared Resources
```

---

## 🤖 Agents (23)

Specialist AI personas for different domains.

| Agent | Focus | Skills Used |
|-------|-------|-------------|
| `orchestrator` | Multi-agent coordination | parallel-agents, behavioral-modes |
| `project-planner` | Discovery, task planning | brainstorming, plan-writing, architecture |
| `frontend-specialist` | Web UI/UX | frontend-design, react-patterns, tailwind-patterns |
| `backend-specialist` | API, business logic | api-patterns, nodejs-best-practices, database-design |
| `database-architect` | Schema, SQL | database-design, prisma-expert |
| `mobile-developer` | iOS, Android, RN | mobile-design |
| `game-developer` | Game logic, mechanics | game-development |
| `devops-engineer` | CI/CD, Docker | deployment-procedures, docker-expert |
| `security-auditor` | Security compliance | vulnerability-scanner, red-team-tactics |
| `penetration-tester` | Offensive security | red-team-tactics |
| `test-engineer` | Testing strategies | testing-patterns, tdd-workflow, webapp-testing |
| `debugger` | Root cause analysis | systematic-debugging |
| `performance-optimizer` | Speed, Web Vitals | performance-profiling |
| `seo-specialist` | Ranking, visibility | seo-fundamentals, geo-fundamentals |
| `documentation-writer` | Manuals, docs | documentation-templates |
| `explorer-agent` | Codebase analysis | - |
| `product-manager` | Product strategy | brainstorming, plan-writing |
| `product-owner` | User stories, backlog | brainstorming |
| `qa-automation-engineer` | QA automation | testing-patterns, webapp-testing |
| `code-archaeologist` | Legacy code analysis | systematic-debugging |
| `**code-reviewer**` | **Code quality & security review** | **security-review, coding-standards** |
| `**researcher**` | **Find existing solutions** | **search-first, architecture** |
| `**refactorer**` | **Code restructuring** | **coding-standards, clean-code** |

---

## 🧠 Skills (50)

Domain-specific knowledge modules. Skills are loaded on-demand based on task context.

### Frontend & UI
| Skill | Description |
|-------|-------------|
| `react-patterns` | React hooks, state, performance |
| `nextjs-best-practices` | App Router, Server Components |
| `tailwind-patterns` | Tailwind CSS v4 utilities |
| `frontend-design` | UI/UX patterns, design systems |
| `ui-ux-pro-max` | 50 styles, 21 palettes, 50 fonts |
| `web-design-guidelines` | Web Interface Guidelines |

### Backend & API
| Skill | Description |
|-------|-------------|
| `api-patterns` | REST, GraphQL, tRPC |
| `nestjs-expert` | NestJS modules, DI, decorators |
| `nodejs-best-practices` | Node.js async, modules |
| `python-patterns` | Python standards, FastAPI |

### Database
| Skill | Description |
|-------|-------------|
| `database-design` | Schema design, optimization |
| `prisma-expert` | Prisma ORM, migrations |

### TypeScript/JavaScript
| Skill | Description |
|-------|-------------|
| `typescript-expert` | Type-level programming, performance |
| `nextjs-react-expert` | React + Next.js optimization |

### Cloud & Infrastructure
| Skill | Description |
|-------|-------------|
| `docker-expert` | Containerization, Compose |
| `deployment-procedures` | CI/CD, deploy workflows |
| `server-management` | Infrastructure management |

### Testing & Quality
| Skill | Description |
|-------|-------------|
| `testing-patterns` | Jest, Vitest, strategies |
| `webapp-testing` | E2E, Playwright |
| `tdd-workflow` | Test-driven development |
| `code-review-checklist` | Code review standards |

### Security
| Skill | Description |
|-------|-------------|
| `vulnerability-scanner` | Security auditing, OWASP |
| `red-team-tactics` | Offensive security |
| `**security-review**` | **Practical OWASP checklist with code examples** |

### Architecture & Planning
| Skill | Description |
|-------|-------------|
| `app-builder` | Full-stack app scaffolding |
| `architecture` | System design patterns |
| `plan-writing` | Task planning, breakdown |
| `brainstorming` | Socratic questioning |
| `**search-first**` | **Research-before-coding workflow** |

### Development Methodology (NEW from ECC)
| Skill | Description |
|-------|-------------|
| `**coding-standards**` | **Immutability, KISS, DRY, YAGNI** |
| `**git-workflow**` | **Conventional commits, PR process** |
| `**continuous-learning**` | **Instinct-based pattern extraction** |
| `**autonomous-loops**` | **Sequential pipeline, De-Sloppify patterns** |

### Mobile
| Skill | Description |
|-------|-------------|
| `mobile-design` | Mobile UI/UX patterns |

### Game Development
| Skill | Description |
|-------|-------------|
| `game-development` | Game logic, mechanics |

### SEO & Growth
| Skill | Description |
|-------|-------------|
| `seo-fundamentals` | SEO, E-E-A-T, Core Web Vitals |
| `geo-fundamentals` | GenAI optimization |

### Shell/CLI
| Skill | Description |
|-------|-------------|
| `bash-linux` | Linux commands, scripting |
| `powershell-windows` | Windows PowerShell |

### Other
| Skill | Description |
|-------|-------------|
| `clean-code` | Coding standards (Global) |
| `behavioral-modes` | Agent personas |
| `parallel-agents` | Multi-agent patterns |
| `mcp-builder` | Model Context Protocol |
| `documentation-templates` | Doc formats |
| `i18n-localization` | Internationalization |
| `performance-profiling` | Web Vitals, optimization |
| `systematic-debugging` | Troubleshooting |
| `intelligent-routing` | Auto agent selection |
| `rust-pro` | Rust development |

---

## 🔄 Workflows (15)

Slash command procedures. Invoke with `/command`.

| Command | Description |
|---------|-------------|
| `/brainstorm` | Socratic discovery |
| `/create` | Create new features |
| `/debug` | Debug issues |
| `/deploy` | Deploy application |
| `/enhance` | Improve existing code |
| `/orchestrate` | Multi-agent coordination |
| `/plan` | Task breakdown |
| `/preview` | Preview changes |
| `/status` | Check project status |
| `/test` | Run tests |
| `/ui-ux-pro-max` | Design with 50 styles |
| `/data-safety` | Data protection rules |
| `**/code-review**` | **Systematic code review** |
| `**/security-check**` | **Pre-deploy security scan** |
| `**/learn**` | **Extract patterns from session** |

---

## 📐 Rules Structure

```
rules/
├── GEMINI.md            # Master orchestrator config
├── common/              # All languages
│   ├── coding-style.md  # Immutability, KISS, DRY
│   ├── git-workflow.md  # Commits, branches, PRs
│   ├── security.md      # Mandatory security checks
│   └── testing.md       # TDD, coverage targets
├── python/              # Python-specific
│   └── style.md         # PEP 8, type hints, async
└── web/                 # JavaScript/TypeScript
    └── style.md         # Strict TS, React, CSS
```

---

## 🎯 Skill Loading Protocol

```
User Request → Skill Description Match → Load SKILL.md
                                            ↓
                                    Read references/
                                            ↓
                                    Read scripts/
```

### Skill Structure

```
skill-name/
├── SKILL.md           # (Required) Metadata & instructions
├── scripts/           # (Optional) Python/Bash scripts
├── references/        # (Optional) Templates, docs
└── assets/            # (Optional) Images, logos
```

---

## 📊 Statistics

| Metric | Value |
|--------|-------|
| **Total Agents** | 23 |
| **Total Skills** | 50 |
| **Total Workflows** | 15 |
| **Rule Categories** | 3 (common, python, web) |
| **Coverage** | ~95% web/mobile/python development |
| **ECC Integration** | ✅ Cherry-picked best practices |

---

## 🔗 Quick Reference

| Need | Agent | Skills |
|------|-------|--------|
| Web App | `frontend-specialist` | react-patterns, nextjs-best-practices |
| API | `backend-specialist` | api-patterns, nodejs-best-practices |
| Python | `backend-specialist` | python-patterns, database-design |
| Mobile | `mobile-developer` | mobile-design |
| Database | `database-architect` | database-design, prisma-expert |
| Security | `security-auditor` | vulnerability-scanner, security-review |
| Testing | `test-engineer` | testing-patterns, webapp-testing |
| Debug | `debugger` | systematic-debugging |
| Plan | `project-planner` | brainstorming, plan-writing |
| Code Review | `code-reviewer` | security-review, coding-standards |
| Research | `researcher` | search-first, architecture |
| Refactor | `refactorer` | coding-standards, clean-code |
| Learn | - | continuous-learning |
