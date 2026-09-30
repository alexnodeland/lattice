import os

# The tests never reach the Hub: fail fast if anything tries.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"
