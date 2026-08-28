from datasets import load_dataset

dataset = load_dataset("mandarjoshi/trivia_qa", "rc", split="validation[:50]")
dataset.to_json("data/raw/triviaqa_control_sample.jsonl")