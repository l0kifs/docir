"""The Tier 1 check rules, grouped by what causes each one to fire.

One module per cause — a schema edit, a ``tags.yaml`` edit, the review clock
and the code tree, the authored relation graph — so a change to one group does
not open the others. ``GraphChecker`` composes them and stays the only caller.
"""
