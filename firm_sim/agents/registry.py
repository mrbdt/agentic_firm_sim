from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from firm_sim.agents.base import AgentConfig, BaseAgent
from firm_sim.agents.ceo import CEOAgent
from firm_sim.agents.researcher import ResearcherAgent
from firm_sim.agents.pm import PMAgent
from firm_sim.agents.risk import RiskAgent
from firm_sim.agents.execution import ExecutionAgent


@dataclass(slots=True)
class LoadedFirmConfig:
    agents: list[AgentConfig]
    watchlist: list[str]


def load_yaml(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_agents(
    config_path: str,
    *,
    bus,
    state,
    llm,
    tools,
    risk_limits: dict[str, Any],
) -> tuple[list[BaseAgent], LoadedFirmConfig]:
    data = load_yaml(config_path)
    firm = data.get("firm") or {}
    watchlist = list(firm.get("watchlist") or [])

    agents_cfg: list[AgentConfig] = []
    for a in (data.get("agents") or []):
        agents_cfg.append(
            AgentConfig(
                id=str(a.get("id")),
                name=str(a.get("name") or a.get("id")),
                title=str(a.get("title") or ""),
                role=str(a.get("role") or ""),
                model=str(a.get("model") or ""),
                heartbeat_seconds=float(a.get("heartbeat_seconds") or 5.0),
                can_trade=bool(a.get("can_trade") or False),
            )
        )

    role_map = {
        "chief_executive_officer": CEOAgent,
        "ceo": CEOAgent,
        "research": ResearcherAgent,
        "portfolio_manager": PMAgent,
        "pm": PMAgent,
        "risk": RiskAgent,
        "execution": ExecutionAgent,
        "exec": ExecutionAgent,
    }

    agents: list[BaseAgent] = []
    for cfg in agents_cfg:
        cls = role_map.get(cfg.role, BaseAgent)
        agents.append(
            cls(
                cfg,
                bus=bus,
                state=state,
                llm=llm,
                tools=tools,
                watchlist=watchlist,
                risk_limits=risk_limits,
            )
        )

    return agents, LoadedFirmConfig(agents=agents_cfg, watchlist=watchlist)
