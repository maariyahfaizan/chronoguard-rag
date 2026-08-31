from datasets import load_dataset
import random

random.seed(42)
dataset = load_dataset("mandarjoshi/trivia_qa", "rc", split="validation")
indices = random.sample(range(len(dataset)), 100)
sample = dataset.select(indices)

print(sample[0])
print(f"Total examples loaded: {len(sample)}")