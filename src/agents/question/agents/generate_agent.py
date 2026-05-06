#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GenerateAgent - Responsible for generating questions based on knowledge context.

Uses unified BaseAgent for LLM calls and configuration management.
"""

import json
import re
import hashlib
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.question.quality import normalize_question_type


class GenerateAgent(BaseAgent):
    """
    Agent responsible for generating questions from knowledge context.

    Responsibilities:
    - Generate questions based on requirements and knowledge
    - Support both custom mode (from scratch) and mimic mode (from reference)
    - Output structured question JSON
    """

    def __init__(
        self,
        language: str = "en",
        **kwargs,
    ):
        """
        Initialize GenerateAgent.

        Args:
            language: Language for prompts ("en" or "zh")
            **kwargs: Additional arguments passed to BaseAgent
        """
        super().__init__(
            module_name="question",
            agent_name="generate_agent",
            language=language,
            **kwargs,
        )

    async def process(
        self,
        requirement: dict[str, Any],
        knowledge_context: str,
        focus: dict[str, Any] | None = None,
        reference_question: str | None = None,
    ) -> dict[str, Any]:
        """
        Main processing: generate a question.

        Args:
            requirement: Question requirement dict (knowledge_point, difficulty, question_type, etc.)
            knowledge_context: Retrieved knowledge summary
            focus: Optional focus/angle for the question
            reference_question: Optional reference question for mimic mode

        Returns:
            Dict with:
                - success: Whether generation succeeded
                - question: Generated question dict (if success)
                - error: Error message (if failed)
        """
        self.logger.info("Starting question generation")

        # Resolve requested question type (focus type has higher priority)
        raw_type = None
        if focus and focus.get("type"):
            raw_type = str(focus.get("type"))
        elif requirement.get("question_type"):
            raw_type = str(requirement.get("question_type"))
        requested_type = normalize_question_type(raw_type, fallback="written")
        effective_requirement = dict(requirement)
        effective_requirement["question_type"] = requested_type
        requirements_str = json.dumps(effective_requirement, ensure_ascii=False, indent=2)

        # Build focus string
        if focus:
            focus_str = f"Focus: {focus.get('focus', '')}\nType: {focus.get('type', requirement.get('question_type', 'written'))}"
        else:
            focus_str = f"Type: {requirement.get('question_type', 'written')}"

        # Choose prompt based on mode
        if reference_question:
            # Mimic mode
            return await self._generate_with_reference(
                requirements_str=requirements_str,
                knowledge_context=knowledge_context,
                reference_question=reference_question,
            )
        else:
            # Custom mode
            return await self._generate_custom(
                requirements_str=requirements_str,
                knowledge_context=knowledge_context,
                focus_str=focus_str,
                knowledge_point=requirement.get("knowledge_point", ""),
                requested_type=requested_type,
            )

    async def _generate_custom(
        self,
        requirements_str: str,
        knowledge_context: str,
        focus_str: str,
        knowledge_point: str,
        requested_type: str,
    ) -> dict[str, Any]:
        """
        Generate a custom question (not based on reference).

        Args:
            requirements_str: JSON string of requirements
            knowledge_context: Retrieved knowledge summary
            focus_str: Focus/angle description
            knowledge_point: Main knowledge point

        Returns:
            Dict with success status and question/error
        """
        system_prompt = self.get_prompt("system", "")
        user_prompt_template = self.get_prompt("generate", "")

        if not user_prompt_template:
            # Fallback prompt
            user_prompt_template = (
                "Generate a question based on:\n"
                "Requirements: {requirements}\n"
                "Focus: {focus}\n"
                "Knowledge: {knowledge}\n\n"
                "Return JSON with question_type, question, correct_answer, explanation."
            )

        user_prompt = user_prompt_template.format(
            requirements=requirements_str,
            focus=focus_str,
            knowledge=knowledge_context[:4000]
            if len(knowledge_context) > 4000
            else knowledge_context,
        )
        schema_hint = self._build_type_specific_schema_hint(requested_type)
        user_prompt = f"{user_prompt}\n\n{schema_hint}"

        try:
            response = await self.call_llm(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                response_format={"type": "json_object"},
                stage="generate_question",
            )

            question = self._parse_question_response(response, requested_type=requested_type)
            question["knowledge_point"] = knowledge_point

            self.logger.info(f"Generated {question.get('question_type', 'unknown')} question")

            return {
                "success": True,
                "question": question,
            }

        except Exception as e:
            self.logger.error(f"Question generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    async def _generate_with_reference(
        self,
        requirements_str: str,
        knowledge_context: str,
        reference_question: str,
    ) -> dict[str, Any]:
        """
        Generate a question based on a reference (mimic mode).

        Args:
            requirements_str: JSON string of requirements
            knowledge_context: Retrieved knowledge summary
            reference_question: Reference question text

        Returns:
            Dict with success status and question/error
        """
        system_prompt = self.get_prompt("system", "")
        user_prompt_template = self.get_prompt("generate_with_reference", "")

        if not user_prompt_template:
            # Fallback prompt
            user_prompt_template = (
                "Generate a new question inspired by the reference but distinct:\n"
                "Reference: {reference_question}\n"
                "Requirements: {requirements}\n"
                "Knowledge: {knowledge}\n\n"
                "Return JSON with question_type, question, correct_answer, explanation."
            )

        user_prompt = user_prompt_template.format(
            reference_question=reference_question,
            requirements=requirements_str,
            knowledge=knowledge_context[:4000]
            if len(knowledge_context) > 4000
            else knowledge_context,
        )

        try:
            response = await self.call_llm(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                response_format={"type": "json_object"},
                stage="generate_with_reference",
            )

            question = self._parse_question_response(
                response,
                requested_type=normalize_question_type("written"),
            )

            self.logger.info(f"Generated mimic {question.get('question_type', 'unknown')} question")

            return {
                "success": True,
                "question": question,
            }

        except Exception as e:
            self.logger.error(f"Reference-based generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def _parse_question_response(
        self,
        response: str,
        requested_type: str = "written",
    ) -> dict[str, Any]:
        """
        Parse LLM response into question dict.

        Uses robust JSON extraction that handles:
        - Markdown code blocks
        - Control characters in LaTeX formulas
        - Python triple-quoted strings
        - Partial JSON extraction

        Args:
            response: LLM response string

        Returns:
            Parsed question dict

        Raises:
            ValueError: If parsing fails
        """
        if not response or not response.strip():
            raise ValueError("LLM returned empty response")

        # Try to extract JSON from markdown code blocks if present
        json_content = self._extract_json_from_markdown(response)

        # Clean control characters that may break JSON parsing
        json_content = self._clean_json_string(json_content)

        # Try multiple parsing strategies
        question = None
        parse_error = None

        # Strategy 1: Direct parse
        try:
            question = json.loads(json_content)
        except json.JSONDecodeError as e:
            parse_error = e

        # Strategy 2: Try extracting JSON object pattern
        if question is None:
            json_obj_pattern = re.compile(r"\{[\s\S]*\}")
            match = json_obj_pattern.search(json_content)
            if match:
                try:
                    question = json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass

        # Strategy 3: Try fixing common LLM JSON issues
        if question is None:
            try:
                fixed_content = self._fix_common_json_issues(json_content)
                question = json.loads(fixed_content)
            except json.JSONDecodeError:
                pass

        if question is None:
            raise ValueError(f"Failed to parse question JSON: {parse_error}") from parse_error

        # Validate required fields
        if "question" not in question:
            raise ValueError("Question response missing 'question' field")

        # The requested type is the UI contract. Keep it authoritative because
        # the model can drift from multiple_choice back to choice.
        question["question_type"] = requested_type

        # Validate options for choice questions
        if question.get("question_type") == "choice":
            options = question.get("options")
            if not options:
                # Create default options if missing
                self.logger.warning("Choice question missing options, adding placeholder")
                question["options"] = {
                    "A": "Option A (placeholder)",
                    "B": "Option B (placeholder)",
                    "C": "Option C (placeholder)",
                    "D": "Option D (placeholder)",
                }
            elif not isinstance(options, dict):
                # Convert to dict if it's a list or other format
                self.logger.warning(f"Options is not a dict: {type(options)}, converting")
                if isinstance(options, list):
                    question["options"] = {
                        chr(65 + i): str(opt) for i, opt in enumerate(options[:4])
                    }
                else:
                    question["options"] = {"A": str(options)}
            elif len(options) < 2:
                self.logger.warning(f"Choice question has only {len(options)} options")
            question = self._refine_choice_question(question)
        elif question.get("question_type") == "multiple_choice":
            options = question.get("options")
            if not isinstance(options, dict):
                if isinstance(options, list):
                    options = {chr(65 + i): str(opt) for i, opt in enumerate(options[:6])}
                else:
                    options = {}
            question["options"] = options
            question = self._refine_multiple_choice_question(question)

        # Fill-blank canonical fields
        if question.get("question_type") == "fill_blank":
            if not isinstance(question.get("blanks"), list):
                question["blanks"] = self._split_values(str(question.get("correct_answer", "")))
            if not question["blanks"] and question.get("correct_answer"):
                question["blanks"] = [str(question.get("correct_answer")).strip()]

        return question

    def _refine_choice_question(self, question: dict[str, Any]) -> dict[str, Any]:
        """
        Two-stage distractor quality enhancement:
        1) candidate cleanup and normalization
        2) deterministic ranking/selection for diversity and plausibility
        """
        options = question.get("options") if isinstance(question.get("options"), dict) else {}
        cleaned_pairs = self._clean_option_candidates(options)
        if not cleaned_pairs:
            cleaned_pairs = [
                ("A", "Option A"),
                ("B", "Option B"),
                ("C", "Option C"),
                ("D", "Option D"),
            ]

        answer_label = str(question.get("correct_answer", "")).strip().upper()
        answer_text = ""
        if answer_label and answer_label in dict(cleaned_pairs):
            answer_text = str(dict(cleaned_pairs).get(answer_label, "")).strip()
        elif answer_label and answer_label not in {"A", "B", "C", "D"}:
            answer_text = answer_label

        if not answer_text:
            answer_text = str(cleaned_pairs[0][1]).strip()

        original_count = len(options)
        unique_count = len(cleaned_pairs)
        distractor_candidates = [(k, v) for k, v in cleaned_pairs if v.strip() != answer_text.strip()]
        selected = self._select_best_distractors(
            stem=str(question.get("question", "")),
            correct_answer=answer_text,
            candidates=[v for _, v in distractor_candidates],
            target=3,
        )

        final_values = [answer_text] + selected
        while len(final_values) < 4:
            final_values.append(f"Distractor {len(final_values)}")
        final_values = self._stable_shuffle_options(
            final_values[:4],
            seed_text=f"{question.get('question', '')}|{answer_text}",
        )

        final_options: dict[str, str] = {}
        labels = ["A", "B", "C", "D"]
        correct_new_label = "A"
        for idx, val in enumerate(final_values):
            label = labels[idx]
            final_options[label] = val
            if val == answer_text:
                correct_new_label = label

        question["options"] = final_options
        question["correct_answer"] = correct_new_label
        question["explanation"] = self._realign_explanation_labels(
            explanation=str(question.get("explanation", "")),
            old_labels=[answer_label] if answer_label in {"A", "B", "C", "D"} else [],
            new_labels=[correct_new_label],
        )
        question["distractor_meta"] = {
            "candidate_count": max(0, unique_count - 1),
            "selected_count": max(0, len(final_values) - 1),
            "duplicate_removed": max(0, original_count - unique_count),
        }
        return question

    def _refine_multiple_choice_question(self, question: dict[str, Any]) -> dict[str, Any]:
        options = question.get("options") if isinstance(question.get("options"), dict) else {}
        original_count = len(options)
        cleaned_pairs = self._clean_option_candidates(options)
        if not cleaned_pairs:
            cleaned_pairs = [
                ("A", "Option A"),
                ("B", "Option B"),
                ("C", "Option C"),
                ("D", "Option D"),
            ]

        raw_answers = [
            x.strip().upper()
            for x in re.split(r"[,;/|\s]+", str(question.get("correct_answer", "")))
            if x.strip()
        ]
        base_map = dict(cleaned_pairs)
        correct_texts: list[str] = []
        for a in raw_answers:
            if a in base_map:
                correct_texts.append(base_map[a])
        if not correct_texts and cleaned_pairs:
            correct_texts = [cleaned_pairs[0][1]]

        distractor_candidates = [v for _, v in cleaned_pairs if v not in correct_texts]
        selected = self._select_best_distractors(
            stem=str(question.get("question", "")),
            correct_answer="; ".join(correct_texts),
            candidates=distractor_candidates,
            target=max(2, 5 - len(correct_texts)),
        )

        final_values = correct_texts + selected
        if len(final_values) < 4:
            for _, v in cleaned_pairs:
                if v not in final_values:
                    final_values.append(v)
                if len(final_values) >= 4:
                    break
        while len(final_values) < 4:
            final_values.append(f"Distractor {len(final_values)}")
        final_values = self._stable_shuffle_options(
            final_values[:6],
            seed_text=f"{question.get('question', '')}|{';'.join(correct_texts)}",
        )

        labels = ["A", "B", "C", "D", "E", "F"]
        final_options: dict[str, str] = {}
        answer_labels: list[str] = []
        for idx, val in enumerate(final_values):
            label = labels[idx]
            final_options[label] = val
            if val in correct_texts:
                answer_labels.append(label)

        if not answer_labels:
            answer_labels = ["A"]
        question["options"] = final_options
        question["correct_answer"] = ",".join(sorted(answer_labels))
        question["explanation"] = self._realign_explanation_labels(
            explanation=str(question.get("explanation", "")),
            old_labels=[x for x in raw_answers if x in base_map],
            new_labels=answer_labels,
        )
        question["distractor_meta"] = {
            "candidate_count": max(0, len(cleaned_pairs) - len(correct_texts)),
            "selected_count": max(0, len(final_values) - len(correct_texts)),
            "duplicate_removed": max(0, original_count - len(cleaned_pairs)),
        }
        return question

    @staticmethod
    def _stable_shuffle_options(values: list[str], seed_text: str) -> list[str]:
        indexed = list(enumerate(values))

        def key(item: tuple[int, str]) -> str:
            idx, value = item
            material = f"{seed_text}|{idx}|{value}".encode("utf-8", errors="ignore")
            return hashlib.sha256(material).hexdigest()

        return [value for _, value in sorted(indexed, key=key)]

    @staticmethod
    def _realign_explanation_labels(
        explanation: str,
        old_labels: list[str],
        new_labels: list[str],
    ) -> str:
        if not explanation or not old_labels or not new_labels:
            return explanation

        old_answer = ",".join(sorted(dict.fromkeys(x.upper() for x in old_labels if x)))
        new_answer = ",".join(sorted(dict.fromkeys(x.upper() for x in new_labels if x)))
        if not old_answer or old_answer == new_answer:
            return explanation

        replacements = [
            (rf"答案\s*(?:是|为|:|：)?\s*{re.escape(old_answer)}\b", f"答案为{new_answer}"),
            (rf"正确答案\s*(?:是|为|:|：)?\s*{re.escape(old_answer)}\b", f"正确答案为{new_answer}"),
            (rf"选择\s*{re.escape(old_answer)}\b", f"选择{new_answer}"),
            (rf"选\s*{re.escape(old_answer)}\b", f"选{new_answer}"),
            (rf"answer\s*(?:is|:)?\s*{re.escape(old_answer)}\b", f"answer is {new_answer}"),
            (rf"correct answer\s*(?:is|:)?\s*{re.escape(old_answer)}\b", f"correct answer is {new_answer}"),
            (rf"option\s*{re.escape(old_answer)}\b", f"option {new_answer}"),
        ]
        updated = explanation
        for pattern, replacement in replacements:
            updated = re.sub(pattern, replacement, updated, flags=re.IGNORECASE)
        return updated

    @staticmethod
    def _clean_option_candidates(options: dict[str, Any]) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        seen_values: set[str] = set()
        for key, value in options.items():
            label = str(key).strip().upper()[:1] or "A"
            text = str(value).strip()
            if not text:
                continue
            norm = re.sub(r"\s+", " ", text.lower())
            if norm in seen_values:
                continue
            seen_values.add(norm)
            pairs.append((label, text))
        pairs.sort(key=lambda x: x[0])
        return pairs

    def _select_best_distractors(
        self,
        stem: str,
        correct_answer: str,
        candidates: list[str],
        target: int = 3,
    ) -> list[str]:
        if not candidates:
            return []

        correct_tokens = self._tokenize_for_quality(correct_answer)
        stem_tokens = self._tokenize_for_quality(stem)

        def score(c: str) -> tuple[float, float]:
            tokens = self._tokenize_for_quality(c)
            overlap_correct = len(tokens & correct_tokens)
            overlap_stem = len(tokens & stem_tokens)
            length_penalty = abs(len(c) - max(1, len(correct_answer))) / max(1, len(correct_answer))
            quality = (0.8 * overlap_stem) - (0.9 * overlap_correct) - (0.25 * length_penalty)
            diversity_anchor = -float(len(tokens))
            return (quality, diversity_anchor)

        unique: list[str] = []
        seen: set[str] = set()
        for c in candidates:
            norm = re.sub(r"\s+", " ", c.strip().lower())
            if not norm or norm in seen:
                continue
            if norm == re.sub(r"\s+", " ", correct_answer.strip().lower()):
                continue
            seen.add(norm)
            unique.append(c.strip())

        ranked = sorted(unique, key=score, reverse=True)
        return ranked[: max(0, target)]

    @staticmethod
    def _tokenize_for_quality(text: str) -> set[str]:
        zh_words = re.findall(r"[\u4e00-\u9fa5]{2,}", text or "")
        en_words = re.findall(r"[a-zA-Z]{3,}", (text or "").lower())
        return set(zh_words + en_words)

    @staticmethod
    def _split_values(raw: str) -> list[str]:
        return [x.strip() for x in re.split(r"[,;|\n]+", raw or "") if x.strip()]

    @staticmethod
    def _pairs_from_answer(raw: str) -> list[dict[str, str]]:
        pairs: list[dict[str, str]] = []
        chunks = [x.strip() for x in (raw or "").split("||") if x.strip()]
        for chunk in chunks:
            left, right = "", ""
            if "=>" in chunk:
                left, right = chunk.split("=>", 1)
            elif ":" in chunk:
                left, right = chunk.split(":", 1)
            elif "-" in chunk:
                left, right = chunk.split("-", 1)
            if left.strip() and right.strip():
                pairs.append({"left": left.strip(), "right": right.strip()})
        return pairs

    @staticmethod
    def _split_order_steps(raw: str) -> list[str]:
        return [x.strip() for x in re.split(r"->|=>|,|;", raw or "") if x.strip()]

    @staticmethod
    def _build_type_specific_schema_hint(requested_type: str) -> str:
        common = (
            "Output requirements: return JSON object only, no markdown code block. "
            "Required fields: question_type, question, correct_answer, explanation."
        )
        if requested_type == "choice":
            return f"{common}\nSingle-choice: options must include A/B/C/D. correct_answer must be one of A/B/C/D."
        if requested_type == "multiple_choice":
            return (
                f"{common}\n"
                "Multiple-choice: question_type must be exactly multiple_choice. "
                "The stem must clearly ask for multiple correct answers, e.g. "
                "'Which of the following statements are correct?'. "
                "options must include A/B/C/D. correct_answer must contain at "
                "least two comma-separated labels, e.g. A,C."
            )
        if requested_type == "true_false":
            return f"{common}\nTrue/false: options fixed as A=True, B=False; correct_answer must be A or B."
        if requested_type == "fill_blank":
            return f"{common}\nFill-blank: provide blanks array in order; correct_answer joins blank answers with commas."
        return common

    def _clean_json_string(self, json_str: str) -> str:
        """
        Clean JSON string by removing/escaping problematic characters.

        Handles:
        - Control characters (0x00-0x1f except tab, newline, carriage return)
        - Unescaped newlines inside string values
        """
        if not json_str:
            return json_str

        # Remove most control characters but keep \t, \n, \r
        # These can appear in LLM output and break JSON parsing
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", json_str)

        return cleaned

    def _fix_common_json_issues(self, content: str) -> str:
        """
        Attempt to fix common JSON issues from LLM output.

        Fixes:
        - Python triple-quoted strings converted to JSON strings
        - Trailing commas before closing braces/brackets
        """
        if not content:
            return content

        # Fix Python triple-quoted strings (LLMs sometimes generate these)
        def replace_triple_quotes(match: re.Match) -> str:
            inner = match.group(1)
            # Use json.dumps to properly escape the content
            return json.dumps(inner)

        content = re.sub(r'"""([\s\S]*?)"""', replace_triple_quotes, content)

        # Remove trailing commas before } or ]
        content = re.sub(r",\s*([}\]])", r"\1", content)

        return content

    def _extract_json_from_markdown(self, content: str) -> str:
        """
        Extract JSON from markdown code blocks.

        LLMs often wrap JSON in ```json ... ``` blocks. This method strips
        the markdown formatting and any surrounding text.

        Args:
            content: Raw LLM response

        Returns:
            Extracted JSON string
        """
        if not content:
            return content

        # Try to find JSON code block
        json_block_pattern = r"```(?:json)?\s*\n?(.*?)```"
        matches = re.findall(json_block_pattern, content, re.DOTALL)

        if matches:
            # Return the content inside the first code block
            return matches[0].strip()

        # If no code blocks found, return as-is (might already be valid JSON)
        return content.strip()
