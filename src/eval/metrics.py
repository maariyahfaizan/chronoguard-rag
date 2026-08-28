# src/eval/metrics.py
import re
import string


def normalize_answer(text: str) -> str:
    """Standard SQuAD/TriviaQA-style normalization: lowercase, strip punctuation,
    remove articles, collapse whitespace."""
    text = text.lower()
    text = "".join(ch for ch in text if ch not in string.punctuation)
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    text = " ".join(text.split())
    return text


def exact_match(prediction: str, gold_answer: str, gold_aliases: list[str] = None) -> int:
    """Returns 1 if normalized prediction matches gold_answer or any gold_alias exactly, else 0."""
    gold_list = [gold_answer] + (gold_aliases or [])
    pred_norm = normalize_answer(prediction)
    return int(any(pred_norm == normalize_answer(g) for g in gold_list))


def f1_score(prediction: str, gold_answer: str, gold_aliases: list[str] = None) -> float:
    """Token-overlap F1 between prediction and gold, taking the max across gold_answer + gold_aliases."""
    gold_list = [gold_answer] + (gold_aliases or [])
    pred_tokens = normalize_answer(prediction).split()

    best_f1 = 0.0
    for gold in gold_list:
        gold_tokens = normalize_answer(gold).split()

        if not pred_tokens or not gold_tokens:
            # Both empty -> perfect match; one empty -> zero overlap
            f1 = 1.0 if pred_tokens == gold_tokens else 0.0
            best_f1 = max(best_f1, f1)
            continue

        common = {}
        for tok in pred_tokens:
            common[tok] = min(pred_tokens.count(tok), gold_tokens.count(tok))
        num_common = sum(common.values())

        if num_common == 0:
            continue

        precision = num_common / len(pred_tokens)
        recall = num_common / len(gold_tokens)
        f1 = 2 * precision * recall / (precision + recall)
        best_f1 = max(best_f1, f1)

    return best_f1