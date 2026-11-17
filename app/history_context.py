"""Fit history by dropping whole old user turns, keeping tool exchanges paired."""
def fit_history(messages, encode, budget):
    current = list(messages)
    while True:
        tokens = encode(current)
        if len(tokens) <= budget:
            return tokens
        users = [i for i, m in enumerate(current) if m.get('role') == 'user']
        if len(users) < 2:
            raise ValueError('The latest turn and system instructions exceed the local context limit')
        # Keep every system instruction, and everything from the next user onward.
        boundary = users[1]
        current = [m for m in current[:boundary] if m.get('role') == 'system'] + current[boundary:]
