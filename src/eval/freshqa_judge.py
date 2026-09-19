"""
FreshEval-style correctness judging for FreshQA, per freshqa_report.md 2c
and the research plan's Section 7 ("Exact Match/F1 or benchmark
accuracy" -- FreshQA is where the "or" is exercised, using the full
published FreshEval rubric, per the scoring-effort decision).

Rubric implemented (all 4 criteria from the FreshQA/FreshLLMs paper):
  1. Relaxed Criteria: hallucinations, outdated info, and ill-formed
     answers are all acceptable AS LONG AS the primary answer is
     accurate.
  2. Confident Answers Required: credit only if the response gives a
     confident, definitive answer, or the correct answer can be
     obviously inferred. Hedged/non-answers ("I'm not sure", "it could
     be X or Y") do not get credit even if X happens to be right.
  3. False Premise Handling: for false_premise == "TRUE" questions, the
     response MUST explicitly point out the false premise to get credit
     -- correctly answering "around" the false premise without flagging
     it does not count.
  4. Name Accuracy: for answers naming entities/people, the response
     needs the complete name or a commonly recognized form, not a vague
     partial reference.
  5. Numerical Precision: approximate numbers are NOT accepted unless
     the gold answer itself is approximate.

JUDGE MODEL: generate.py exposes load_model() (Mistral-7B-Instruct, 4-bit,
local, no API) and a chat-template-based generation path, but
generate_answer() itself is QA-specific -- it forces the "Context:...
Question:...Answer:" template via build_prompt(), which is wrong for a
judging prompt. _call_judge_model() below instead applies the same
tokenizer.apply_chat_template()/model.generate() mechanics directly to
the FreshEval prompt, bypassing build_prompt() entirely.

judge_model is expected to be a (model, tokenizer) tuple -- the SAME kind
of tuple load_model() returns. Per the research plan, only one local
open-weights model (Mistral-7B) is specified for the full runs, with a
second model family reserved for the smaller transfer study, and no
separate/stronger model is set aside for judging -- so the default here
is to reuse the SAME (model, tokenizer) already loaded for generation as
the judge, i.e. Mistral-7B judges its own (and every retriever
config's) answers.

CAVEAT, worth stating explicitly in the paper's methodology section:
FreshQA's own published numbers were judged with GPT-4. A 7B local model
judging under the same rubric will not be equivalent in judge quality --
self-judging with a small model is a real, known source of noise/bias
(e.g. weaker instruction-following on the "confident answer required"
and "false premise" rules specifically, which need more careful reading
than plain fact-matching). This doesn't block running the pipeline, but
the FreshEval numbers should be reported as "Mistral-7B-judged FreshEval
accuracy," not bare "FreshEval accuracy," and are not directly comparable
to FreshQA's own published GPT-4-judged numbers without noting that
difference. If a stronger/separate judge model becomes available later,
pass it as judge_model explicitly and nothing else in this file needs to
change.
"""

import json
import re


JUDGE_PROMPT_TEMPLATE = """You are grading a model's answer to a question, using the FreshEval rubric. Follow these rules exactly:

1. Relaxed Criteria: hallucinations, outdated information, and ill-formed answers are all acceptable AS LONG AS the primary answer is accurate.
2. Confident Answers Required: only give credit if the response provides a confident, definitive answer, or the correct answer can be obviously inferred from it. A hedged or non-committal answer does NOT get credit, even if it mentions the correct answer as one of several possibilities.
3. False Premise Handling: this question {false_premise_clause}. {false_premise_instruction}
4. Name Accuracy: if the answer involves the name of an entity (e.g. a person), the response must give the complete name or a commonly recognized form of it, not a vague or partial reference.
5. Numerical Precision: approximate numbers are NOT acceptable unless the ground-truth answer itself is approximate.

Question: {question}

Ground-truth answer (and acceptable aliases): {gold_answers}

Model's answer: {model_answer}

Respond with ONLY a JSON object, no other text, no markdown fences:
{{"correct": true or false, "rationale": "one sentence explaining the verdict against the rubric above"}}"""


def _build_judge_prompt(question, model_answer, gold_answer, gold_aliases, false_premise):
    gold_answers = ", ".join([gold_answer] + list(gold_aliases or []))

    is_false_premise = str(false_premise).strip().upper() == "TRUE"
    if is_false_premise:
        false_premise_clause = "DOES contain a false premise"
        false_premise_instruction = (
            "The response MUST explicitly point out that the question's premise is false "
            "to receive credit -- correctly working around the false premise without naming "
            "it as false does NOT count."
        )
    else:
        false_premise_clause = "does not contain a false premise"
        false_premise_instruction = "This rule does not apply -- judge normally on rules 1, 2, 4, 5."

    return JUDGE_PROMPT_TEMPLATE.format(
        question=question,
        gold_answers=gold_answers,
        model_answer=model_answer,
        false_premise_clause=false_premise_clause,
        false_premise_instruction=false_premise_instruction,
    )


def _parse_judge_response(raw_response):
    """
    Parse the judge model's JSON response. Strips markdown code fences if
    the judge model added them despite being told not to (common failure
    mode), and falls back to a regex scan for `"correct": true/false` if
    json.loads fails outright, so one malformed response doesn't crash a
    whole run. Returns {"correct": None, "rationale": "..."} if parsing
    fails entirely -- None (not False) because "the judge call broke" is a
    different fact from "the judge said incorrect", and should not be
    silently counted as either in aggregate_metrics.
    """
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw_response.strip(), flags=re.MULTILINE).strip()

    try:
        parsed = json.loads(cleaned)
        return {
            "correct": bool(parsed["correct"]),
            "rationale": str(parsed.get("rationale", "")),
        }
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    match = re.search(r'"correct"\s*:\s*(true|false)', cleaned, re.IGNORECASE)
    if match:
        return {
            "correct": match.group(1).lower() == "true",
            "rationale": f"[unparsed rationale -- raw response: {cleaned[:200]}]",
        }

    return {
        "correct": None,
        "rationale": f"[judge response could not be parsed: {cleaned[:200]}]",
    }


JUDGE_MAX_NEW_TOKENS = 200  # rubric + JSON rationale needs more room than
                            # generate_answer's 64-token QA-answer budget


def _call_judge_model(prompt, judge_model):
    """
    Raw prompt -> text completion, using the same chat-template mechanics
    as generate.py's generate_answer(), but WITHOUT routing through
    build_prompt() -- the judge prompt (JUDGE_PROMPT_TEMPLATE above) is
    already complete and must not be wrapped in the QA "Context:...
    Question:...Answer:" template.

    judge_model must be a (model, tokenizer) tuple, e.g. whatever
    load_model() returned for generation -- see module docstring for why
    reusing the generator model as judge is the current default.
    """
    model, tokenizer = judge_model

    messages = [{"role": "user", "content": prompt}]
    inputs = tokenizer.apply_chat_template(
        messages,
        return_tensors="pt",
        add_generation_prompt=True,
        return_dict=True,
    ).to(model.device)

    output_ids = model.generate(
        **inputs,
        max_new_tokens=JUDGE_MAX_NEW_TOKENS,
        do_sample=False,
        pad_token_id=tokenizer.eos_token_id,
    )

    generated = output_ids[0][inputs["input_ids"].shape[-1]:]
    return tokenizer.decode(generated, skip_special_tokens=True).strip()


def judge_answer(question, model_answer, gold_answer, gold_aliases, false_premise, judge_model=None):
    """
    Returns {"correct": bool | None, "rationale": str} for one FreshQA
    question, using the full FreshEval rubric above. `correct` is None if
    the judge call itself failed (raised, or returned unparseable output)
    -- callers (e.g. run_baseline_freshqa.py) should treat None the same
    way metrics.py treats None everywhere else: excluded from averages,
    never coerced to 0.
    """
    if judge_model is None:
        raise ValueError(
            "judge_answer() needs judge_model=(model, tokenizer) -- pass the same "
            "tuple load_model() returned for generation, unless using a separate "
            "judge model (see module docstring)."
        )

    prompt = _build_judge_prompt(
        question=question,
        model_answer=model_answer,
        gold_answer=gold_answer,
        gold_aliases=gold_aliases,
        false_premise=false_premise,
    )

    try:
        raw_response = _call_judge_model(prompt, judge_model)
    except Exception as e:
        return {"correct": None, "rationale": f"[judge call raised: {e}]"}

    return _parse_judge_response(raw_response)