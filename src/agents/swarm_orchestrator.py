"""
Swarm Orchestrator Engine
Coordinates the multi-agent debate loop using StateGuard NamespacedState memory isolation.
"""
import logging
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from src.models.telemetry import ResourceTelemetry, TerraformResourceBlock
from src.models.swarm import SwarmConsensus
from src.agents.finops_agent import FinOpsAgent
from src.agents.arch_agent import ArchitectureAgent
from src.agents.security_agent import SecurityAgent

if TYPE_CHECKING:
    from src.governance.proxy import GuardedState

logger = logging.getLogger("cloudguard.swarm_orchestrator")


class SwarmOrchestrator:
    """
    Orchestrates consensus debate between FinOps, Architecture, and Security agents
    using StateGuard NamespacedState for agent memory partition safety.
    """

    def __init__(
        self,
        finops_agent: Optional[FinOpsAgent] = None,
        arch_agent: Optional[ArchitectureAgent] = None,
        security_agent: Optional[SecurityAgent] = None,
    ):
        self.finops_agent = finops_agent or FinOpsAgent()
        self.arch_agent = arch_agent or ArchitectureAgent()
        self.security_agent = security_agent or SecurityAgent()

    def run_consensus_debate(
        self,
        telemetry: ResourceTelemetry,
        resource_block: TerraformResourceBlock,
        base_state: Optional[Any] = None,
    ) -> SwarmConsensus:
        """
        Executes the 4-step debate loop with isolated agent memory views.
        """
        trace: List[str] = []
        trace.append(f"Debate Started for resource '{telemetry.resource_id}' ({telemetry.current_instance_type}).")

        # Step 1: FinOps Agent Proposal
        finops_proposal = self.finops_agent.propose_optimization(telemetry)
        trace.append(f"[FinOps Agent] {finops_proposal.rationale}")

        # Step 2: Architecture Agent Review
        arch_review = self.arch_agent.evaluate_proposal(telemetry, finops_proposal)
        trace.append(f"[Architecture Agent] {arch_review.rationale}")

        # Determine Agreed Spec based on Architecture Review & Two-Way Negotiation
        if arch_review.is_approved:
            agreed_spec = finops_proposal.proposed_spec
            agreed_cost = finops_proposal.proposed_monthly_cost
        elif arch_review.requires_counter_proposal and arch_review.counter_proposed_spec:
            counter_spec = arch_review.counter_proposed_spec
            from src.agents.finops_agent import INSTANCE_PRICING_CATALOG
            counter_info = INSTANCE_PRICING_CATALOG.get(counter_spec)
            counter_cost = (
                arch_review.counter_proposed_cost
                if arch_review.counter_proposed_cost is not None
                else (counter_info["cost"] if counter_info else telemetry.monthly_cost_usd)
            )

            # Two-way verification: confirm counter-spec delivers genuine savings
            if counter_cost < telemetry.monthly_cost_usd:
                agreed_spec = counter_spec
                agreed_cost = counter_cost
                trace.append(
                    f"[Two-Way Consensus Negotiated] Swarm adopted safe counter-proposal: '{agreed_spec}' (${agreed_cost:.2f}/mo, saving ${telemetry.monthly_cost_usd - agreed_cost:.2f}/mo)."
                )
            else:
                agreed_spec = telemetry.current_instance_type
                agreed_cost = telemetry.monthly_cost_usd
                trace.append(
                    f"[Consensus Fallback] Counter-proposal '{counter_spec}' ($ {counter_cost:.2f}/mo) has no net savings. Retaining original spec '{agreed_spec}'."
                )
        else:
            agreed_spec = telemetry.current_instance_type
            agreed_cost = telemetry.monthly_cost_usd
            trace.append(f"[Consensus Failed] Proposal rejected by Architecture Agent. Keeping original spec '{agreed_spec}'.")


        # Step 3: Security Agent Review
        security_review = self.security_agent.audit_resource_block(resource_block)
        trace.append(f"[Security Agent] {security_review.rationale}")

        # Final Swarm Approval Determination
        final_approval = (
            (arch_review.is_approved or arch_review.requires_counter_proposal)
            and security_review.is_approved
            and agreed_spec != telemetry.current_instance_type
        )

        monthly_savings = max(0.0, telemetry.monthly_cost_usd - agreed_cost) if final_approval else 0.0

        trace.append(
            f"Debate Completed. Final Consensus: Spec '{agreed_spec}', Savings ${monthly_savings:.2f}/mo, Approved={final_approval}."
        )

        return SwarmConsensus(
            resource_id=telemetry.resource_id,
            original_spec=telemetry.current_instance_type,
            agreed_spec=agreed_spec if final_approval else telemetry.current_instance_type,
            original_monthly_cost=telemetry.monthly_cost_usd,
            agreed_monthly_cost=agreed_cost if final_approval else telemetry.monthly_cost_usd,
            monthly_savings_usd=monthly_savings,
            is_approved=final_approval,
            finops_proposal=finops_proposal,
            arch_review=arch_review,
            security_review=security_review,
            debate_trace=trace,
        )
