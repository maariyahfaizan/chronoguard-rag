from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
import torch


def load_model(model_name: str = "mistralai/Mistral-7B-Instruct-v0.2"):
    """Load Mistral in 4-bit on whatever GPU is available (Kaggle T4)."""
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    quant_config = BitsAndBytesConfig(load_in_4bit=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        dtype=torch.float16,
        quantization_config=quant_config,
        device_map="auto",
    )
    return model, tokenizer


def build_prompt(query: str, candidates: list[str], max_passage_chars: int = 1500) -> str:
    """Concatenate retrieved passages into a context block + question."""
    context = "\n\n".join(c[:max_passage_chars] for c in candidates)
    return (
        f"Answer the question using only the context below.\n"
        f"Answer with only the specific fact requested — a name, date, or short phrase.\n"
        f"Do not answer in a full sentence and do not add explanation.\n"
        f"If the answer is not in the context, say 'unknown'.\n\n"
        f"Context:\n{context}\n\nQuestion: {query}\nAnswer:"
    )


def generate_answer(query: str, candidates: list[str], model, tokenizer, max_new_tokens: int = 64) -> str:
    """Generate an answer using a locally-loaded Mistral model (no API calls)."""
    prompt = build_prompt(query, candidates)
    messages = [{"role": "user", "content": prompt}]

    inputs = tokenizer.apply_chat_template(
        messages,
        return_tensors="pt",
        add_generation_prompt=True,
        return_dict=True,
    ).to(model.device)

    output_ids = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        do_sample=False,
        pad_token_id=tokenizer.eos_token_id,
    )

    generated = output_ids[0][inputs["input_ids"].shape[-1]:]
    return tokenizer.decode(generated, skip_special_tokens=True).strip()