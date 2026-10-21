"""An agent fixture with a bounded tool branch; it has no long-term memory."""
MAX_STEPS = 2


def route(state):
    if state['steps'] >= MAX_STEPS:
        return 'finish'
    return 'tool' if state.get('tool_call') else 'finish'


def execute(state, tool):
    if route(state) == 'tool':
        result = tool(state['tool_call'])
        return {**state, 'steps': state['steps'] + 1, 'tool_result': result}
    return state
