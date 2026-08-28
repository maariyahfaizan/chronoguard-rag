from datasets import load_dataset

dataset = load_dataset("mandarjoshi/trivia_qa", "rc", split="validation[:50]")

print(dataset[0])
print(f"Total examples loaded: {len(dataset)}")