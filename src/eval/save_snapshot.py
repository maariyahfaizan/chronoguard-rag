from datasets import load_dataset
import random

random.seed(42)
dataset = load_dataset("mandarjoshi/trivia_qa", "rc", split="validation")
indices = random.sample(range(len(dataset)), 100)
sample = dataset.select(indices)

sample.to_json("data/raw/triviaqa_control_sample.jsonl")