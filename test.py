import os

# Read ./temp/tom/prompt.json
with open(os.path.join(os.path.dirname(__file__), 'temp', 'tom', 'prompt.json')) as f:
    print(f.read().splitlines())
