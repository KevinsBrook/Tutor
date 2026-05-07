#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AgentCoordinator - Orchestrates question generation workflow.

Refactored version:
- Uses specialized agents: RetrieveAgent, GenerateAgent, RelevanceAnalyzer
- No iterative validation loops - single-pass generation + relevance analysis
- All questions are accepted, classified as "high" or "partial" relevance
"""

from collections.abc import Callable
from datetime import datetime
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import sys
from typing import Any

# Add project root for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.logging import Logger, get_logger
from src.services.config import load_config_with_main

from .agents.generate_agent import GenerateAgent
from .quality import build_question_audit, normalize_question_schema, normalize_question_type
from .agents.relevance_analyzer import RelevanceAnalyzer
from .repository import JsonQuestionRunRepository, QuestionRunRepository
from .agents.retrieve_agent import RetrieveAgent

MIXED_QUESTION_TYPE_POOL = ["choice", "multiple_choice", "true_false", "fill_blank", "written"]


class AgentCoordinator:
    """
    Coordinate question generation workflow using specialized agents.

    Workflow:
    1. RetrieveAgent: Generate queries and retrieve knowledge
    2. Plan: Generate question plan with focuses
    3. GenerateAgent: Generate questions
    4. RelevanceAnalyzer: Analyze relevance (no rejection, just classification)
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        max_rounds: int = 10,  # Kept for backward compatibility, but not used for iteration
        kb_name: str | None = None,
        output_dir: str | None = None,
        language: str = "en",
        repository: QuestionRunRepository | None = None,
    ):
        """
        Initialize the coordinator.

        Args:
            api_key: API key (optional, loaded from config if not provided)
            base_url: API endpoint (optional)
            api_version: API version for Azure (optional)
            max_rounds: Deprecated, kept for backward compatibility
            kb_name: Knowledge base name
            output_dir: Output directory for results
            language: Language for prompts ("en" or "zh")
        """
        self.kb_name = kb_name
        self.output_dir = output_dir
        self.language = language
        self.repository = repository or JsonQuestionRunRepository()

        # Store API credentials for creating agents
        self._api_key = api_key
        self._base_url = base_url
        self._api_version = api_version

        # Load configuration
        self.config = load_config_with_main("question_config.yaml", project_root)

        # Initialize logger
        log_dir = self.config.get("paths", {}).get("user_log_dir") or self.config.get(
            "logging", {}
        ).get("log_dir")
        self.logger: Logger = get_logger("QuestionCoordinator", log_dir=log_dir)

        # Get config values
        question_cfg = self.config.get("question", {})
        self.rag_query_count = question_cfg.get("rag_query_count", 3)
        self.max_parallel_questions = question_cfg.get("max_parallel_questions", 1)
        self.rag_mode = question_cfg.get("rag_mode", "naive")

        # Token tracking - will be updated from BaseAgent shared stats
        self.token_stats = {
            "model": "gpt-4o-mini",
            "calls": 0,
            "tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost": 0.0,
        }

        # WebSocket callback for streaming updates
        self._ws_callback: Callable | None = None

    def _update_token_stats(self):
        """Update token_stats from BaseAgent's shared LLMStats for the question module."""
        from src.agents.base_agent import BaseAgent

        try:
            stats = BaseAgent.get_stats("question")
            summary = stats.get_summary()

            self.token_stats = {
                "model": summary.get("model", "gpt-4o-mini"),
                "calls": summary.get("calls", 0),
                "tokens": summary.get("total_tokens", 0),
                "input_tokens": summary.get("input_tokens", 0),
                "output_tokens": summary.get("output_tokens", 0),
                "cost": summary.get("cost", 0.0),
            }
        except Exception as e:
            self.logger.debug(f"Failed to update token stats: {e}")

    def set_ws_callback(self, callback: Callable):
        """Set WebSocket callback for streaming updates to frontend."""
        self._ws_callback = callback

    async def _send_ws_update(self, update_type: str, data: dict[str, Any]):
        """Send update via WebSocket callback if available."""
        if self._ws_callback:
            try:
                await self._ws_callback({"type": update_type, **data})
            except Exception as e:
                self.logger.debug(f"Failed to send WS update: {e}")

    def _create_retrieve_agent(self) -> RetrieveAgent:
        """Create a RetrieveAgent instance."""
        return RetrieveAgent(
            kb_name=self.kb_name,
            rag_mode=self.rag_mode,
            language=self.language,
            api_key=self._api_key,
            base_url=self._base_url,
            api_version=self._api_version,
        )

    def _create_generate_agent(self) -> GenerateAgent:
        """Create a GenerateAgent instance."""
        return GenerateAgent(
            language=self.language,
            api_key=self._api_key,
            base_url=self._base_url,
            api_version=self._api_version,
        )

    def _create_relevance_analyzer(self) -> RelevanceAnalyzer:
        """Create a RelevanceAnalyzer instance."""
        return RelevanceAnalyzer(
            language=self.language,
            api_key=self._api_key,
            base_url=self._base_url,
            api_version=self._api_version,
        )

    def _has_kb_source(self) -> bool:
        return bool(str(self.kb_name or "").strip())

    def _build_direct_knowledge_context(self, requirement: dict[str, Any]) -> str:
        topic = str(requirement.get("knowledge_point") or "").strip()
        difficulty = str(requirement.get("difficulty") or "medium")
        question_type = str(requirement.get("question_type") or "written")
        cognitive_level = str(requirement.get("cognitive_level") or "understand")
        extra = str(requirement.get("additional_requirements") or "").strip()
        return (
            "No external knowledge base was selected. Generate the question directly from "
            "the teacher-provided knowledge point and constraints.\n"
            f"Knowledge point: {topic}\n"
            f"Difficulty: {difficulty}\n"
            f"Question type: {question_type}\n"
            f"Cognitive level: {cognitive_level}\n"
            f"Additional requirements: {extra}"
        )

    # =========================================================================
    # Main Entry Points
    # =========================================================================

    async def generate_question(
        self,
        requirement: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate a single question with relevance analysis.

        This is used by Mimic mode and for single question generation.

        Args:
            requirement: Question requirement dict

        Returns:
            Dict with:
                - success: bool
                - question: Generated question dict
                - analysis: Relevance analysis result
                - rounds: Always 1 (no iteration)
        """
        self.logger.section("Single Question Generation")
        self.logger.info(f"Knowledge point: {requirement.get('knowledge_point', 'N/A')}")
        requirement = dict(requirement)
        avoid_questions = self._collect_avoid_questions(requirement)
        if avoid_questions:
            requirement["additional_requirements"] = self._merge_additional_requirements(
                requirement.get("additional_requirements"),
                self._build_anti_repeat_context(avoid_questions),
            )

        await self._send_ws_update(
            "progress", {"stage": "generating", "progress": {"status": "initializing"}}
        )

        # Step 1: Retrieve knowledge, or use the manual topic directly when no KB is selected.
        if self._has_kb_source():
            retrieve_agent = self._create_retrieve_agent()
            retrieval_result = await retrieve_agent.process(
                requirement=requirement,
                num_queries=self.rag_query_count,
            )

            if not retrieval_result.get("has_content"):
                self.logger.warning("No relevant knowledge found")
                return {
                    "success": False,
                    "error": "knowledge_not_found",
                    "message": "Knowledge base does not contain relevant information.",
                }

            knowledge_context = retrieval_result["summary"]
            source_refs = self._build_source_refs(retrieval_result.get("retrievals", []))
        else:
            knowledge_context = self._build_direct_knowledge_context(requirement)
            source_refs = []

        # Step 2: Generate question
        generate_agent = self._create_generate_agent()

        # Check if this is mimic mode (has reference_question)
        reference_question = requirement.get("reference_question")

        gen_result: dict[str, Any] = {}
        question: dict[str, Any] | None = None
        duplicate_warning = ""
        for attempt in range(3):
            attempt_requirement = dict(requirement)
            attempt_requirement["avoid_questions"] = avoid_questions
            if attempt > 0:
                attempt_requirement["additional_requirements"] = self._merge_additional_requirements(
                    attempt_requirement.get("additional_requirements"),
                    "The previous candidate was too similar to a previous question. "
                    "Use a clearly different stem, scenario, numbers, and reasoning path.",
                )
            gen_result = await generate_agent.process(
                requirement=attempt_requirement,
                knowledge_context=knowledge_context,
                reference_question=reference_question,
            )

            if not gen_result.get("success"):
                break

            raw_requested_type = str(requirement.get("question_type", "written") or "written").lower()
            requested_type = (
                "mixed" if raw_requested_type == "mixed" else normalize_question_type(raw_requested_type)
            )
            candidate = normalize_question_schema(
                gen_result["question"],
                requested_type=requested_type,
                cognitive_level=requirement.get("cognitive_level", "understand"),
            )
            similar_to = self._find_similar_question(candidate.get("question", ""), avoid_questions)
            if similar_to and attempt < 2:
                self.logger.warning("Generated question is too similar to a previous stem; retrying")
                continue
            if similar_to:
                duplicate_warning = "Generated question may still be similar to a previous question."
            question = candidate
            break

        if not gen_result.get("success") or question is None:
            self.logger.error(f"Question generation failed: {gen_result.get('error')}")
            return {
                "success": False,
                "error": gen_result.get("error", "Generation failed"),
            }

        question["source_refs"] = source_refs
        if duplicate_warning:
            question["duplicate_warning"] = duplicate_warning

        # Step 3: Analyze relevance
        analyzer = self._create_relevance_analyzer()
        analysis = await analyzer.process(
            question=question,
            knowledge_context=knowledge_context,
        )

        self.logger.success(f"Question generated with {analysis['relevance']} relevance")

        # Build result (compatible with old format)
        result = {
            "success": True,
            "question": question,
            "validation": {
                "decision": "approve",  # Always approve
                "relevance": analysis["relevance"],
                "kb_coverage": analysis["kb_coverage"],
                "extension_points": analysis.get("extension_points", ""),
                "audit": build_question_audit(
                    question=question,
                    requested_difficulty=requirement.get("difficulty", "medium"),
                    relevance=analysis["relevance"],
                    kb_coverage=analysis["kb_coverage"],
                    source_refs=source_refs,
                ),
            },
            "rounds": 1,  # No iteration
        }

        # Save to disk if output_dir is set
        if self.output_dir:
            self._save_question_result(result, requirement)

        # Update token stats from shared LLMStats
        self._update_token_stats()

        return result

    async def generate_questions_custom(
        self,
        requirement: dict[str, Any],
        num_questions: int,
    ) -> dict[str, Any]:
        """
        Custom mode: Generate multiple questions from a requirement.

        Flow:
        1. Researching: Retrieve background knowledge
        2. Planning: Generate question plan with focuses
        3. Generating: Generate each question + relevance analysis

        Args:
            requirement: Base requirement dict (knowledge_point, difficulty, question_type)
            num_questions: Number of questions to generate

        Returns:
            Summary dict with all results
        """
        if num_questions <= 0:
            raise ValueError("num_questions must be greater than zero")

        self.logger.section(f"Custom Mode Generation: {num_questions} question(s)")
        requirement = dict(requirement)
        avoid_questions = self._collect_avoid_questions(requirement)
        generated_stems = list(avoid_questions)
        if avoid_questions:
            requirement["additional_requirements"] = self._merge_additional_requirements(
                requirement.get("additional_requirements"),
                self._build_anti_repeat_context(avoid_questions),
            )

        # Create batch directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        batch_dir = Path(self.output_dir) / f"batch_{timestamp}" if self.output_dir else None
        if batch_dir:
            batch_dir.mkdir(parents=True, exist_ok=True)

        # =====================================================================
        # Stage 1: Researching
        # =====================================================================
        self.logger.stage("Stage 1: Researching")
        await self._send_ws_update(
            "progress",
            {"stage": "researching", "progress": {"status": "retrieving"}, "total": num_questions},
        )

        if self._has_kb_source():
            retrieve_agent = self._create_retrieve_agent()
            retrieval_result = await retrieve_agent.process(
                requirement=requirement,
                num_queries=self.rag_query_count,
            )

            if not retrieval_result.get("has_content"):
                self.logger.warning("No relevant knowledge found")
                return {
                    "success": False,
                    "error": "knowledge_not_found",
                    "message": "Knowledge base does not contain relevant information.",
                    "search_queries": retrieval_result.get("queries", []),
                }

            knowledge_context = retrieval_result["summary"]
            queries = retrieval_result["queries"]
            source_refs = self._build_source_refs(retrieval_result.get("retrievals", []))
        else:
            retrieval_result = {
                "has_content": True,
                "summary": self._build_direct_knowledge_context(requirement),
                "queries": [],
                "retrievals": [],
            }
            knowledge_context = retrieval_result["summary"]
            queries = []
            source_refs = []

        raw_requested_type = str(requirement.get("question_type", "written") or "written").lower()
        resolved_type = (
            "mixed" if raw_requested_type == "mixed" else normalize_question_type(raw_requested_type)
        )
        cognitive_level = requirement.get("cognitive_level", "understand")

        # Save knowledge.json
        if batch_dir:
            self.repository.save_knowledge(batch_dir, retrieval_result)

        await self._send_ws_update("knowledge_saved", {"queries": queries})

        # =====================================================================
        # Stage 2: Planning
        # =====================================================================
        self.logger.stage("Stage 2: Planning")
        await self._send_ws_update(
            "progress", {"stage": "planning", "progress": {"status": "creating_plan"}}
        )

        plan = await self._generate_question_plan(requirement, knowledge_context, num_questions)
        focuses = plan.get("focuses", [])

        # Save plan.json
        if batch_dir:
            self.repository.save_plan(batch_dir, plan)

        await self._send_ws_update("plan_ready", {"plan": plan, "focuses": focuses})

        # =====================================================================
        # Stage 3: Generating
        # =====================================================================
        self.logger.stage("Stage 3: Generating")
        await self._send_ws_update(
            "progress",
            {"stage": "generating", "progress": {"current": 0, "total": num_questions}},
        )

        results = []
        failures = []

        generate_agent = self._create_generate_agent()
        analyzer = self._create_relevance_analyzer()

        for idx, focus in enumerate(focuses):
            question_id = focus.get("id", f"q_{idx + 1}")
            self.logger.info(f"Generating question {question_id}")

            await self._send_ws_update(
                "question_update",
                {
                    "question_id": question_id,
                    "status": "generating",
                    "focus": focus.get("focus", ""),
                },
            )

            question = None
            gen_result: dict[str, Any] = {}
            duplicate_warning = ""
            max_attempts = 3
            for attempt in range(max_attempts):
                attempt_requirement = dict(requirement)
                attempt_requirement["avoid_questions"] = generated_stems[-20:]
                if attempt > 0:
                    attempt_requirement["additional_requirements"] = (
                        self._merge_additional_requirements(
                            attempt_requirement.get("additional_requirements"),
                            "The previous candidate was too similar to an earlier question. "
                            "Create a clearly different stem, scenario, numbers, or reasoning path.",
                        )
                    )

                gen_result = await generate_agent.process(
                    requirement=attempt_requirement,
                    knowledge_context=knowledge_context,
                    focus=focus,
                )

                if not gen_result.get("success"):
                    break

                candidate = normalize_question_schema(
                    gen_result["question"],
                    requested_type=normalize_question_type(focus.get("type", resolved_type)),
                    cognitive_level=cognitive_level,
                )
                similar_to = self._find_similar_question(candidate.get("question", ""), generated_stems)
                if similar_to and attempt < max_attempts - 1:
                    self.logger.warning(
                        f"Generated question {question_id} is too similar to a previous stem; retrying"
                    )
                    continue
                if similar_to:
                    duplicate_warning = "Generated question may still be similar to a previous question."
                question = candidate
                break

            if not gen_result.get("success") or question is None:
                self.logger.error(f"Failed to generate question {question_id}")
                failures.append(
                    {
                        "question_id": question_id,
                        "error": gen_result.get("error", "Unknown error"),
                    }
                )
                await self._send_ws_update(
                    "question_update", {"question_id": question_id, "status": "error"}
                )
                continue

            question["source_refs"] = source_refs
            if duplicate_warning:
                question["duplicate_warning"] = duplicate_warning

            # Analyze relevance
            await self._send_ws_update(
                "question_update", {"question_id": question_id, "status": "analyzing"}
            )

            analysis = await analyzer.process(
                question=question,
                knowledge_context=knowledge_context,
            )

            # Build validation dict (compatible with frontend)
            validation = {
                "decision": "approve",
                "relevance": analysis["relevance"],
                "kb_coverage": analysis["kb_coverage"],
                "extension_points": analysis.get("extension_points", ""),
                "audit": build_question_audit(
                    question=question,
                    requested_difficulty=requirement.get("difficulty", "medium"),
                    relevance=analysis["relevance"],
                    kb_coverage=analysis["kb_coverage"],
                    source_refs=source_refs,
                ),
            }

            # Save result
            result = {
                "question_id": question_id,
                "focus": focus,
                "question": question,
                "analysis": analysis,
                "validation": validation,  # For frontend compatibility
            }
            if duplicate_warning:
                result["duplicate_warning"] = duplicate_warning

            if batch_dir:
                self.repository.save_question_result(batch_dir, result)

            results.append(result)
            generated_stems.append(str(question.get("question") or ""))

            await self._send_ws_update(
                "question_update", {"question_id": question_id, "status": "done"}
            )
            await self._send_ws_update(
                "result",
                {
                    "question_id": question_id,
                    "question": question,
                    "validation": validation,  # Frontend expects 'validation'
                    "focus": focus,
                    "index": idx,
                },
            )
            await self._send_ws_update(
                "progress",
                {"stage": "generating", "progress": {"current": idx + 1, "total": num_questions}},
            )

        # =====================================================================
        # Complete
        # =====================================================================
        summary = {
            "success": len(results) == num_questions,
            "requested": num_questions,
            "completed": len(results),
            "failed": len(failures),
            "search_queries": queries,
            "plan": plan,
            "results": results,
            "failures": failures,
        }

        if batch_dir:
            self.repository.save_summary(batch_dir, summary)
            summary["output_dir"] = str(batch_dir)

        # Update token stats from shared LLMStats
        self._update_token_stats()

        await self._send_ws_update(
            "progress",
            {
                "stage": "complete",
                "completed": len(results),
                "failed": len(failures),
                "total": num_questions,
            },
        )

        self.logger.section("Generation Summary")
        self.logger.info(f"Requested: {num_questions}")
        self.logger.info(f"Completed: {len(results)}")
        self.logger.info(f"Failed: {len(failures)}")

        return summary

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _collect_avoid_questions(self, requirement: dict[str, Any]) -> list[str]:
        values: list[str] = []
        for key in ("avoid_questions", "previous_questions"):
            raw = requirement.get(key)
            if isinstance(raw, list):
                values.extend(str(item).strip() for item in raw)
            elif isinstance(raw, str):
                values.append(raw.strip())
        return self._dedupe_avoid_questions(values)

    def _dedupe_avoid_questions(self, questions: list[str], limit: int = 30) -> list[str]:
        seen: set[str] = set()
        clean: list[str] = []
        for question in questions:
            text = re.sub(r"\s+", " ", str(question or "")).strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            clean.append(text[:500])
        return clean[-limit:]

    def _merge_additional_requirements(self, existing: Any, extra: str) -> str:
        parts = [str(existing or "").strip(), str(extra or "").strip()]
        return "\n\n".join(part for part in parts if part)

    def _build_anti_repeat_context(self, avoid_questions: list[str]) -> str:
        if not avoid_questions:
            return ""
        lines = [
            "Anti-repeat constraint: Do not generate a question that is equivalent or highly similar "
            "to these previous questions. Reuse the same knowledge point, but vary the stem, scenario, "
            "numbers, option wording, and reasoning route."
        ]
        for idx, question in enumerate(avoid_questions[-12:], 1):
            lines.append(f"{idx}. {question}")
        return "\n".join(lines)

    def _question_tokens(self, text: str) -> set[str]:
        normalized = re.sub(r"\s+", "", str(text or "").lower())
        latin_tokens = set(re.findall(r"[a-z0-9]{3,}", normalized))
        cjk = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
        cjk_shingles = {cjk[i : i + 2] for i in range(max(0, len(cjk) - 1))}
        return latin_tokens | cjk_shingles

    def _question_similarity(self, left: str, right: str) -> float:
        left_text = re.sub(r"\s+", " ", str(left or "")).strip().lower()
        right_text = re.sub(r"\s+", " ", str(right or "")).strip().lower()
        if not left_text or not right_text:
            return 0.0
        ratio = SequenceMatcher(None, left_text, right_text).ratio()
        left_tokens = self._question_tokens(left_text)
        right_tokens = self._question_tokens(right_text)
        if not left_tokens or not right_tokens:
            return ratio
        overlap = len(left_tokens & right_tokens)
        jaccard = overlap / max(1, len(left_tokens | right_tokens))
        containment = overlap / max(1, min(len(left_tokens), len(right_tokens)))
        return max(ratio, jaccard, containment)

    def _find_similar_question(
        self,
        candidate: str,
        previous_questions: list[str],
        threshold: float = 0.72,
    ) -> str | None:
        for previous in previous_questions:
            if self._question_similarity(candidate, previous) >= threshold:
                return previous
        return None

    async def _generate_question_plan(
        self,
        requirement: dict[str, Any],
        knowledge_context: str,
        num_questions: int,
    ) -> dict[str, Any]:
        """
        Generate a question plan with distinct focuses.

        Args:
            requirement: Base requirement
            knowledge_context: Retrieved knowledge summary
            num_questions: Number of questions

        Returns:
            Plan dict with focuses array
        """
        from src.services.llm import complete as llm_complete
        from src.services.llm.config import get_llm_config

        llm_config = get_llm_config()
        raw_requested_type = str(requirement.get("question_type", "written") or "written").lower()
        requested_type = (
            "mixed" if raw_requested_type == "mixed" else normalize_question_type(raw_requested_type)
        )
        cognitive_level = requirement.get("cognitive_level", "understand")

        system_prompt = (
            "You are an educational content planner. Create distinct question focuses "
            "that test different aspects of the same topic. If previous questions are provided, "
            "plan focuses that avoid repeating their scenario and reasoning path.\n\n"
            "CRITICAL: Return ONLY valid JSON. Do not wrap in markdown code blocks.\n"
            'Output JSON with key "focuses" containing an array of objects, each with:\n'
            '- "id": string like "q_1", "q_2"\n'
            '- "focus": string describing what aspect to test\n'
            '- "type": one of '
            '["choice","written","true_false","multiple_choice","fill_blank"]\n'
            '- "cognitive_level": one of ["remember","understand","apply","analyze","evaluate","create"]'
        )

        # Truncate knowledge context consistently (4000 chars across all agents)
        truncated_knowledge = (
            knowledge_context[:4000] if len(knowledge_context) > 4000 else knowledge_context
        )
        truncation_suffix = "...[truncated]" if len(knowledge_context) > 4000 else ""
        anti_repeat_context = self._build_anti_repeat_context(
            self._collect_avoid_questions(requirement)
        )

        user_prompt = (
            f"Topic: {requirement.get('knowledge_point', '')}\n"
            f"Difficulty: {requirement.get('difficulty', 'medium')}\n"
            f"Question Type: {requested_type}\n"
            f"Bloom Level: {cognitive_level}\n"
            f"Number: {num_questions}\n\n"
            f"Knowledge:\n{truncated_knowledge}{truncation_suffix}\n\n"
            f"{anti_repeat_context}\n\n"
            f"Generate exactly {num_questions} distinct focuses in JSON."
        )

        try:
            response = await llm_complete(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=llm_config.model,
                api_key=self._api_key or llm_config.api_key,
                base_url=self._base_url or llm_config.base_url,
                api_version=self._api_version,
                response_format={"type": "json_object"},
                temperature=0.3,
            )

            data = json.loads(response)
            focuses = data.get("focuses", [])
            if not isinstance(focuses, list):
                focuses = []

        except Exception as e:
            self.logger.warning(f"Failed to generate plan: {e}")
            focuses = []

        # Fallback: create simple focuses
        requested_types = requirement.get("question_types")
        if not isinstance(requested_types, list):
            requested_types = []
        normalized_type_pool = [
            normalize_question_type(x) for x in requested_types if isinstance(x, str)
        ]
        normalized_type_pool = list(dict.fromkeys(normalized_type_pool))
        if not normalized_type_pool:
            if requested_type == "mixed":
                normalized_type_pool = MIXED_QUESTION_TYPE_POOL
            else:
                normalized_type_pool = [requested_type]

        if len(focuses) < num_questions:
            for i in range(len(focuses), num_questions):
                selected_type = normalized_type_pool[i % len(normalized_type_pool)]
                focuses.append(
                    {
                        "id": f"q_{i + 1}",
                        "focus": f"Aspect {i + 1} of {requirement.get('knowledge_point', 'topic')}",
                        "type": selected_type,
                        "cognitive_level": cognitive_level,
                    }
                )

        for idx, focus in enumerate(focuses):
            fallback_type = normalized_type_pool[idx % len(normalized_type_pool)]
            if requested_type == "mixed":
                focus["type"] = fallback_type
            else:
                # For explicit single-type batches, the requested type is the
                # contract. Do not let the planning LLM quietly turn
                # multiple_choice into choice.
                focus["type"] = requested_type
            focus["cognitive_level"] = focus.get("cognitive_level", cognitive_level)

        return {
            "knowledge_point": requirement.get("knowledge_point", ""),
            "difficulty": requirement.get("difficulty", "medium"),
            "question_type": requested_type,
            "cognitive_level": cognitive_level,
            "num_questions": num_questions,
            "focuses": focuses[:num_questions],
        }

    def _build_source_refs(self, retrievals: list[dict[str, Any]]) -> list[dict[str, str]]:
        refs: list[dict[str, str]] = []
        for idx, item in enumerate(retrievals[:3]):
            query = str(item.get("query", "")).strip()
            answer = str(item.get("answer", "")).strip()
            if not answer:
                continue
            snippet = answer.replace("\n", " ")
            if len(snippet) > 180:
                snippet = snippet[:180].rstrip() + "..."
            refs.append(
                {
                    "id": f"ref_{idx + 1}",
                    "query": query or f"检索片段 {idx + 1}",
                    "snippet": snippet,
                }
            )
        return refs

    def _save_question_result(
        self,
        result: dict[str, Any],
        requirement: dict[str, Any],
    ) -> str | None:
        """Save a single question result to disk."""
        if not self.output_dir:
            return None

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = Path(self.output_dir) / f"question_{timestamp}"
            output_path.mkdir(parents=True, exist_ok=True)

            # Save result.json
            with open(output_path / "result.json", "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            # Save question.md
            question = result.get("question", {})
            validation = result.get("validation", {})

            md_content = f"""# Generated Question

**Knowledge point**: {requirement.get("knowledge_point", question.get("knowledge_point", "N/A"))}
**Difficulty**: {requirement.get("difficulty", "N/A")}
**Type**: {question.get("question_type", "N/A")}
**Relevance**: {validation.get("relevance", "N/A")}

---

## Question
{question.get("question", "")}

"""
            if question.get("options"):
                md_content += "## Options\n"
                for key, value in question.get("options", {}).items():
                    md_content += f"- **{key}**: {value}\n"
                md_content += "\n"

            md_content += f"""
## Answer
{question.get("correct_answer", "")}

## Explanation
{question.get("explanation", "")}

---

## Relevance Analysis

**KB Coverage**: {validation.get("kb_coverage", "")}
"""
            if validation.get("extension_points"):
                md_content += f"\n**Extension Points**: {validation.get('extension_points', '')}"

            with open(output_path / "question.md", "w", encoding="utf-8") as f:
                f.write(md_content)

            self.logger.info(f"Result saved to: {output_path}")
            return str(output_path)

        except Exception as e:
            self.logger.warning(f"Failed to save result: {e}")
            return None

    def _save_knowledge_json(
        self,
        batch_dir: Path,
        retrieval_result: dict[str, Any],
    ):
        """Save knowledge.json for a batch."""
        knowledge_file = batch_dir / "knowledge.json"
        with open(knowledge_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "queries": retrieval_result.get("queries", []),
                    "retrievals": retrieval_result.get("retrievals", []),
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

    def _save_plan_json(self, batch_dir: Path, plan: dict[str, Any]):
        """Save plan.json for a batch."""
        plan_file = batch_dir / "plan.json"
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)

    def _save_custom_question_result(
        self,
        batch_dir: Path,
        result: dict[str, Any],
    ):
        """Save a single question result in custom mode."""
        question_id = result.get("question_id", "q_unknown")
        question_dir = batch_dir / question_id
        question_dir.mkdir(parents=True, exist_ok=True)

        # Save result.json
        with open(question_dir / "result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        # Save question.md
        question = result.get("question", {})
        analysis = result.get("analysis", {})
        focus = result.get("focus", {})

        md_content = f"""# Generated Question

**Focus**: {focus.get("focus", "N/A")}
**Type**: {question.get("question_type", "N/A")}
**Relevance**: {analysis.get("relevance", "N/A")}

---

## Question
{question.get("question", "")}

"""
        if question.get("options"):
            md_content += "## Options\n"
            for key, value in question.get("options", {}).items():
                md_content += f"- **{key}**: {value}\n"
            md_content += "\n"

        md_content += f"""
## Answer
{question.get("correct_answer", "")}

## Explanation
{question.get("explanation", "")}

---

## Relevance Analysis

**KB Coverage**: {analysis.get("kb_coverage", "")}
"""
        if analysis.get("extension_points"):
            md_content += f"\n**Extension Points**: {analysis.get('extension_points', '')}"

        with open(question_dir / "question.md", "w", encoding="utf-8") as f:
            f.write(md_content)
