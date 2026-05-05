"""
redteam4rag/engine/orchestrator.py

Orchestrator — wraps a LangGraph StateGraph to run attacks concurrently.
Each graph invocation handles one AttackPayload; concurrency is managed
with asyncio.Semaphore.
"""

from __future__ import annotations

import asyncio
import datetime
import uuid
from typing import Any

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from redteam4rag.core.config import ScanConfig
from redteam4rag.core.attack_config_loader import AttackConfig
from redteam4rag.engine.state import AttackPayload, AttackState
from redteam4rag.engine.mutation import SearchStrategyFactory
from redteam4rag.generators.static import StaticProbeGenerator
from redteam4rag.conversation.base import ConversationStrategyFactory
from redteam4rag.judges.registry import JudgeRegistry
from redteam4rag.models import (
    AttackResult,
    AttackStatus,
    JudgeContext,
    JudgeVerdict,
    Probe,
    RawResponse,
    ScanMetadata,
    ScanResult,
    Severity,
)
from redteam4rag.providers.base import LLMProviderFactory

# Ensure judges are registered
import redteam4rag.judges.registry  # noqa: F401


class Orchestrator:
    """
    Orchestrates a red-team scan over all attack payloads.

    Each attack payload is executed in its own LangGraph invocation.
    Up to ``config.concurrency`` invocations run in parallel.
    """

    def __init__(
        self,
        config: ScanConfig,
        attack_config: AttackConfig,
        adapter,
        forced_judge_spec: str | None = None,
    ) -> None:
        self._config = config
        self._attack_config = attack_config
        self._adapter = adapter
        self._forced_judge_spec = forced_judge_spec

        # Build judge provider once
        self._judge_provider = LLMProviderFactory.create(
            config.judge_provider,
            config.anthropic_api_key.get_secret_value(),
            config.judge_model,
        )

        # Build and compile the LangGraph graph
        self._app = self._build_graph()

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_graph(self):
        """Build and compile the LangGraph StateGraph."""
        g = StateGraph(AttackState)

        g.add_node("executor", self._executor_node)
        g.add_node("judge", self._judge_node)
        g.add_node("regenerator", self._regenerator_node)

        g.set_entry_point("executor")
        g.add_edge("executor", "judge")
        g.add_conditional_edges(
            "judge",
            self._route_after_judge,
            {
                "regenerator": "regenerator",
                "end": END,
            },
        )
        g.add_conditional_edges(
            "regenerator",
            self._route_after_regenerator,
            {
                "executor": "executor",
                "end": END,
            },
        )

        return g.compile(checkpointer=MemorySaver())

    # ------------------------------------------------------------------
    # Graph nodes
    # ------------------------------------------------------------------

    async def _executor_node(self, state: AttackState) -> dict:
        """Send probes for the current attack and collect responses."""
        if state.get("dry_run", False):
            return {
                "responses": [],
                "conversation_history": [],
                "conversation_metadata": {},
            }

        current_attack: AttackPayload = state["current_attack"]

        strategy = ConversationStrategyFactory.create(
            current_attack.query, strategy_name="static"
        )
        await strategy.initialize(current_attack.query)

        responses: list[RawResponse] = []
        history: list[tuple[str, RawResponse]] = []
        current_verdict: JudgeVerdict | None = state.get("verdict")

        while True:
            next_query = await strategy.next_turn(history, current_verdict)
            if next_query is None:
                break

            probe = Probe(query=next_query)
            try:
                raw_response = await self._adapter.query(probe)
            except Exception as exc:
                raw_response = RawResponse(
                    status_code=None,
                    body={},
                    response_text=f"Error: {exc}",
                )

            responses.append(raw_response)
            history.append((next_query, raw_response))

        return {
            "responses": responses,
            "conversation_history": history,
            "conversation_metadata": strategy.get_metadata(),
        }

    async def _judge_node(self, state: AttackState) -> dict:
        """Evaluate the attack responses and produce a verdict + AttackResult."""
        current_attack: AttackPayload = state["current_attack"]
        responses: list[RawResponse] = state.get("responses", [])
        existing_results: list = state.get("results", [])

        # --- Dry-run: dummy PASS verdict ---
        if state.get("dry_run", False):
            dummy_verdict = JudgeVerdict(
                passed=True,
                reasoning="dry-run: no real evaluation",
                confidence=None,
                judge_name="dry-run",
            )
            attack_result = AttackResult(
                id=AttackResult.make_id(),
                attack_name=current_attack.spec.name,
                category=current_attack.spec.category.value,
                severity=current_attack.spec.severity,
                status=AttackStatus.PASSED,
                query=current_attack.query,
                retrieved_chunks=[],
                response="",
                judge_verdict=dummy_verdict,
                evidence={},
                latency_ms=0.0,
            )
            return {
                "verdict": dummy_verdict,
                "results": existing_results + [attack_result],
            }

        # --- No responses: errored attack ---
        if not responses:
            error_verdict = JudgeVerdict(
                passed=True,
                reasoning="No responses received",
                confidence=None,
                judge_name="error",
            )
            attack_result = AttackResult(
                id=AttackResult.make_id(),
                attack_name=current_attack.spec.name,
                category=current_attack.spec.category.value,
                severity=current_attack.spec.severity,
                status=AttackStatus.ERRORED,
                query=current_attack.query,
                retrieved_chunks=[],
                response="",
                judge_verdict=error_verdict,
                evidence={},
                latency_ms=0.0,
                error="No responses received",
            )
            return {
                "verdict": error_verdict,
                "results": existing_results + [attack_result],
            }

        # Use the last response for judging
        last_response: RawResponse = responses[-1]

        # Determine which judge to use
        judge_spec_str = self._forced_judge_spec or current_attack.spec.judge_override or self._attack_config.judge

        # Resolve judge from registry
        judge = JudgeRegistry.create(judge_spec_str, provider=self._judge_provider)

        # Build context
        ctx = JudgeContext(
            query=current_attack.query,
            retrieved_chunks=last_response.retrieved_chunks,
            response=last_response.response_text,
            attack_metadata={
                "attack_name": current_attack.spec.name,
                "category": current_attack.spec.category.value,
                "severity": current_attack.spec.severity.value,
                "tags": list(current_attack.spec.tags),
            },
            chunk_details=last_response.chunk_details,
            retrieval_query=last_response.retrieval_query,
            cache_info=last_response.cache_info,
            trace=last_response.trace,
            debug_payload=last_response.debug_payload,
        )

        try:
            verdict = await judge.judge(ctx)
        except Exception as exc:
            verdict = JudgeVerdict(
                passed=True,
                reasoning=f"Judge error: {exc}",
                confidence=None,
                judge_name="error",
            )

        # Build AttackResult
        status = AttackStatus.PASSED if verdict.passed else AttackStatus.FAILED

        attack_result = AttackResult(
            id=AttackResult.make_id(),
            attack_name=current_attack.spec.name,
            category=current_attack.spec.category.value,
            severity=current_attack.spec.severity,
            status=status,
            query=current_attack.query,
            retrieved_chunks=last_response.retrieved_chunks,
            response=last_response.response_text,
            judge_verdict=verdict,
            evidence={
                "status_code": last_response.status_code,
                "latency_ms": last_response.latency_ms,
                "mutation_round": current_attack.mutation_round,
            },
            latency_ms=last_response.latency_ms,
        )

        return {
            "verdict": verdict,
            "results": existing_results + [attack_result],
        }

    def _route_after_judge(self, state: AttackState) -> str:
        """Decide whether to mutate, continue to next attack, or end."""
        verdict: JudgeVerdict | None = state.get("verdict")

        # If verdict failed and mutations are available
        if (
            verdict is not None
            and not verdict.passed
            and state.get("mutation_count", 0) > 0
            and not state.get("mutation_exhausted", True)
        ):
            return "regenerator"

        # More attacks in queue
        if state.get("attack_queue"):
            return "end"  # We use one-payload-per-invocation design; queue is always empty

        return "end"

    def _route_after_regenerator(self, state: AttackState) -> str:
        """Route to executor if we have a new variant, otherwise end."""
        if state.get("mutation_exhausted", True):
            return "end"
        return "executor"

    async def _regenerator_node(self, state: AttackState) -> dict:
        """Generate mutation variants and prepend them to the attack queue."""
        current_attack: AttackPayload = state["current_attack"]
        verdict: JudgeVerdict | None = state.get("verdict")
        mutation_history: list[AttackPayload] = list(state.get("mutation_history", []))

        strategy = SearchStrategyFactory.create(
            self._config.mutation_strategy, self._config
        )
        await strategy.initialize(current_attack, self._config)

        candidates: list[AttackPayload] = []
        if verdict is not None:
            candidates = await strategy.next_candidates(
                current_attack, verdict, prior_variants=mutation_history
            )

        mutation_history.extend(candidates)

        # With one-payload-per-graph design, we can't really add to the queue
        # across invocations. Instead, pick the first candidate as the new current_attack.
        if candidates:
            new_current = candidates[0]
            remaining_candidates = candidates[1:]
        else:
            # No more mutations possible
            return {
                "mutation_exhausted": True,
                "mutation_history": mutation_history,
                "strategy_metadata": strategy.get_metadata(),
                "attack_queue": [],
            }

        return {
            "current_attack": new_current,
            "attack_queue": remaining_candidates,
            "mutation_exhausted": strategy.is_exhausted(),
            "mutation_history": mutation_history,
            "strategy_metadata": strategy.get_metadata(),
            # Reset for next execution
            "responses": [],
            "verdict": None,
            "conversation_history": [],
            "conversation_metadata": {},
        }

    # ------------------------------------------------------------------
    # Payload generation
    # ------------------------------------------------------------------

    def _generate_all_payloads(self) -> list[AttackPayload]:
        """Generate one AttackPayload per AttackSpec (using the first query)."""
        payloads: list[AttackPayload] = []
        for spec in self._attack_config.attacks:
            # Use the first query as the seed for each spec; mutation may expand variants
            query = spec.queries[0] if spec.queries else ""
            payloads.append(AttackPayload(spec=spec, query=query))
        return payloads

    # ------------------------------------------------------------------
    # Public run method
    # ------------------------------------------------------------------

    async def run(self) -> ScanResult:
        """Execute all attacks and return an aggregated ScanResult."""
        started_at = datetime.datetime.now(datetime.UTC).isoformat()
        start_mono = asyncio.get_event_loop().time()

        # --- Dry-run: health check only ---
        if self._config.dry_run:
            await self._adapter.health_check()
            finished_at = datetime.datetime.now(datetime.UTC).isoformat()
            duration = asyncio.get_event_loop().time() - start_mono
            return self._build_scan_result([], started_at, finished_at, duration)

        payloads = self._generate_all_payloads()
        sem = asyncio.Semaphore(self._config.concurrency)

        # Set up rich progress display
        try:
            from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
            progress_ctx = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
            )
            use_progress = True
        except ImportError:
            use_progress = False
            progress_ctx = None

        async def run_one(payload: AttackPayload) -> list[AttackResult]:
            async with sem:
                initial_state: AttackState = {
                    "run_id": str(uuid.uuid4()),
                    "attack_queue": [],
                    "current_attack": payload,
                    "responses": [],
                    "verdict": None,
                    "mutation_count": self._config.mutation_count,
                    "mutation_history": [],
                    "mutation_exhausted": self._config.mutation_count == 0,
                    "conversation_history": [],
                    "conversation_metadata": {},
                    "strategy_metadata": {},
                    "results": [],
                    "dry_run": self._config.dry_run,
                }
                thread_id = str(uuid.uuid4())
                try:
                    final = await self._app.ainvoke(
                        initial_state,
                        config={"configurable": {"thread_id": thread_id}},
                    )
                    return final.get("results", [])
                except Exception as exc:
                    # Build an errored result on unexpected graph failure
                    return [
                        AttackResult(
                            id=AttackResult.make_id(),
                            attack_name=payload.spec.name,
                            category=payload.spec.category.value,
                            severity=payload.spec.severity,
                            status=AttackStatus.ERRORED,
                            query=payload.query,
                            retrieved_chunks=[],
                            response="",
                            judge_verdict=None,
                            evidence={},
                            latency_ms=0.0,
                            error=str(exc),
                        )
                    ]

        if use_progress and progress_ctx is not None:
            with progress_ctx as progress:
                task = progress.add_task(
                    f"[cyan]Running {len(payloads)} attacks...", total=len(payloads)
                )

                async def run_one_with_progress(payload: AttackPayload) -> list[AttackResult]:
                    result = await run_one(payload)
                    progress.advance(task)
                    return result

                all_results = await asyncio.gather(
                    *[run_one_with_progress(p) for p in payloads]
                )
        else:
            all_results = await asyncio.gather(*[run_one(p) for p in payloads])

        flat_results = [r for group in all_results for r in group]
        finished_at = datetime.datetime.now(datetime.UTC).isoformat()
        duration = asyncio.get_event_loop().time() - start_mono

        return self._build_scan_result(flat_results, started_at, finished_at, duration)

    # ------------------------------------------------------------------
    # Result building
    # ------------------------------------------------------------------

    def _build_scan_result(
        self,
        results: list[AttackResult],
        started_at: str,
        finished_at: str,
        duration_seconds: float,
    ) -> ScanResult:
        """Assemble a ScanResult from collected AttackResult objects."""
        metadata = ScanMetadata(
            scan_id=str(uuid.uuid4()),
            target_url=self._config.target_url,
            suite_name=self._attack_config.name,
            judge=self._attack_config.judge,
            generator=self._attack_config.generator,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=round(duration_seconds, 3),
        )
        return ScanResult(metadata=metadata, results=results)
