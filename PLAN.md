# Hackathon plan: Inside the Game

Source: official rules (github.com/microsoft/insidethegamehackathon, `OFFICIAL RULES.md`).

## Deadlines (South Africa time, SAST)

| What | Pacific | SAST |
|---|---|---|
| Registration closes (teammates must register too) | Tue 20 Oct, 12:00 PT | **Tue 20 Oct, 21:00** |
| Submission closes | Tue 27 Oct, 23:59 PT | **Wed 28 Oct, 08:59** |
| Judging | 27 Oct – 10 Nov | |
| Top 6 notified | by 10 Nov | |
| Winners announced | by 20 Nov | |

Aim to submit on **Mon 26 Oct evening**. Do not rely on the last night.

## What the judges score

Stage 1 is pass/fail: fits the theme and visibly uses the required Microsoft technologies.
Stage 2: five criteria, **20% each**. Ties break on Technological Implementation first.

| Criterion | What earns points | Where Pitchside covers it |
|---|---|---|
| Technological Implementation | Synthetic data quality, code quality, hero tech (Foundry, Agent Framework, Azure MCP, Copilot agent mode, Fabric, Azure DBs) | `sim.py` + `realism.py` + tests; Foundry agents |
| Agentic Design & Innovation | Orchestration, MCP, multi-agent collaboration | Director, Analyst, Commentator, Verifier, Localiser, RecapWriter; retry + fallback |
| Real-World Impact | Production-ready, real problem | Overlay JSON contract, SSE feed, Container Apps |
| UX & Presentation | Intuitive UX, clear video, frontend + backend balance | Broadcast UI, persona controls |
| Category adherence | Fits chosen category | Target below |

## Category strategy

A project can win **one Grand Prize and one Category Prize**. Target:

1. **Grand Prize** (all entries are considered)
2. **Best Multi-Agent System** as the category. Judges look for distinct roles, shared state, handoffs, failure recovery, and an outcome one agent could not do. The Verifier + retry + fallback loop is the story.

Backup category: Best Azure Cloud Native Integration (if you go deep on Container Apps, Functions, Event Hubs).

## Must-haves for a valid submission

- [ ] Public GitHub repo, created after 29 Sep (this one is new)
- [ ] Demo video **under 2 minutes**, public on YouTube or Vimeo, showing it running; no club logos, real player names or copyrighted music
- [ ] Short pitch: what it is, which Microsoft/Azure tech, what problem it solves
- [ ] A working link judges can open free until 10 Nov (keep the Azure app running; watch costs)
- [ ] Everything in English
- [ ] Teammates (max 4) all registered; one Representative submits

## 11-day schedule

| Day | Date | Work |
|---|---|---|
| 1 | Fri 16 | Push this repo to a **public** GitHub repo. Run it locally. Create Azure account and a Foundry project with a chat model deployment. |
| 2 | Sat 17 | Switch on Foundry mode (`.env`). Check the Verifier pass rate on 10 matches; tune prompts. |
| 3 | Sun 18 | Move the per-moment pipeline into an Agent Framework **workflow** (sequential/handoff) so the orchestration is framework-native, not just Python calls. Add Foundry evaluations (groundedness) on generated text. |
| 4 | Mon 19 | Expose match tools over **MCP** (get_stats, get_moment_evidence, get_player) so agents call tools instead of receiving everything in the prompt. Ensure teammates are registered (closes Tue 21:00). |
| 5 | Tue 20 | Deploy to **Azure Container Apps**. Optional: write events to Cosmos DB or Event Hubs for the "real-time" story. |
| 6 | Wed 21 | Brief features still missing: pass-quality overlay (distance, accuracy, difficulty), ball speed graphic, speed/distance player tags. More languages in Foundry mode (isiZulu, Afrikaans, Arabic, Hindi make a strong "fans in any market" point). |
| 7 | Thu 22 | Optional wow: spoken recap with Azure AI Speech prebuilt voices. Polish the UI. |
| 8 | Fri 23 | **Feature freeze.** Fix bugs, raise test coverage, write architecture diagram. |
| 9 | Sat 24 | Write the video script; record and edit (under 2:00). |
| 10 | Sun 25 | README, pitch text, testing instructions, screenshots. |
| 11 | Mon 26 | **Submit.** Tue 27 is buffer only. |

## Video outline (≤ 1:55)

1. 0:00 Problem: a scoreline does not tell the story; fans want different things.
2. 0:12 Live match running; a goal overlay with the *why*.
3. 0:35 Same moment, toggled to analyst, then to Spanish, then to "my club".
4. 0:55 Follow-a-player mode.
5. 1:10 Agent trace: Analyst → Commentator → Verifier catching an invented number → retry.
6. 1:30 Realism report and architecture on Azure.
7. 1:45 Full-time recap.

## Competitive notes

Several entries are already public on GitHub with similar five-stage pipelines and Multi-Agent targets. Differentiate on: verified-by-code claims with visible evidence, measured data realism, depth of personalisation, a polished broadcast-style UI, and a clean, honest README.

## Prizes (from the rules)

Per team member: 1st place $4,000 cash + match ticket (~$1,000) + $50 store voucher; 2nd $2,500 + ticket + voucher; each category $1,500 + voucher. Paid as USD e-gift cards; winners handle their own tax (non-US residents may need a W-8BEN). South Africa is not on the excluded list.
