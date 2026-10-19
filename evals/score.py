"""Score extracted insights against gold (Day 3).

Gold: AMI abstractive summaries (decisions, actions) plus the hand-labeled state table
per series. LLM judge matches predicted to gold insights; a sample is hand-audited.
Out: per-insight correct/wrong labels — the risk model's training target.
"""
