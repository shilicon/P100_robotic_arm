import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import bootstrap
from tool_parser import ToolStreamParser

tool = {'type': 'function', 'function': {'name': 'test', 'parameters': {}}}
source = '前文<tool_call>{"name":"test","arguments":{"x":2}}</tool_call>后文'
for split in range(len(source) + 1):
    parser = ToolStreamParser([tool])
    events = parser.feed(source[:split]) + parser.feed(source[split:]) + parser.feed('', final=True)
    assert ''.join(e.get('content', '') for e in events) == '前文后文'
    calls = [c for e in events for c in e.get('tool_calls', [])]
    assert len(calls) == 1 and calls[0]['function']['name'] == 'test'
for invalid in ('<tool_call>{"name":"unknown","arguments":{}}</tool_call>', '<tool_call>{'):
    try:
        ToolStreamParser([tool]).feed(invalid, final=True)
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid tool call accepted')
print('PASS tool tags at every split boundary; unknown/incomplete calls rejected')
