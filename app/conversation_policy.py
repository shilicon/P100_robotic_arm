"""Bounded local request preparation and exact, schema-checked command shortcuts."""
import copy
import json
import re
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILTIN = (ROOT / 'prompts/robot.txt').read_text(encoding='utf-8')
COMPACT = '''你是 RIG-ARM 桌面机械臂。按用户指定语言自然回答，默认中文，不用Markdown。先用一句不超过20字的短句直接回答，再按需补充一句；通常总计不超过80字。不要输出思考过程、代码或工具JSON给用户。
能力仅限本次提供的工具；不会行走，尚无画面识别能力，拍照预览不等于识别。普通聊天、能力询问、假设和否定指令不执行动作。明确动作请求才调用工具，每轮最多一个；无参数工具传空对象。严格遵守整数、范围、方向和单位，不修改越界数值。调用工具时只输出工具调用，不加口头开场。
工具结果accepted仅代表已接受，不能声称开始或完成。失败、忙碌或未知状态如实说明，不重试动作。结束示教保存不授权回放。停止动作会归位，不是断电急停。标定、遥控、激光和拍照必须由用户明确要求。用户明确结束对话时才进入待机。'''
NUMBER = r'(?:\d{1,3}|[零〇一二两三四五六七八九十百]{1,6})'
DENIAL = re.compile(r'不要|先别|别(?:做|执行|鞠躬|点头|转|动)|不许|无需|暂时不|现在不|只是问|只问|如果|假如|假设|不用执行|不执行|(?:解释|翻译|复述|朗读|引用).*|[“”「」『』"\']')
ACTION_WORDS = re.compile(r'鞠躬|行礼|点头|摇头|转|抬|低头|歪头|移动|平移|往|向|懒腰|害羞|撒娇|装死|尾巴|表演|动作|微动|停止|归位|示教|录制|录音|回放|轨迹|取消|音量|声音|屏幕|显示|拍照|照片|摄像|待机|休眠|睡觉|结束对话|退出聊天|激光|标定|校准|遥控|蓝牙|语言|模式|电量|状态|亮度|打开|关闭|开启|关掉|开关|设置|调节|设为|调到|走到')
CAPABILITY = re.compile(r'^(?:你|机器人)?(?:能|会|可以)(?:做什么|干什么|哪些动作|什么动作)[？?。！!]*$')
CAPABILITIES = {
    'self_arm_bow': '鞠躬', 'self_arm_node': '点头', 'self_arm_shake': '摇头',
    'self_arm_stretch': '伸懒腰', 'self_arm_shy': '害羞表演', 'self_arm_coquetry': '撒娇表演',
    'self_arm_apology': '道歉表演', 'self_arm_feign_death': '装死表演', 'self_arm_wag_tail': '摇尾巴表演',
    'self_arm_yaw': '头部旋转', 'self_arm_y': '头部平移', 'self_arm_stop': '停止动作并归位',
    'self_arm_idle_motion': '空闲微动', 'self_arm_teach_start': '示教录制', 'self_arm_teach_play': '示教回放',
    'self_audio_speaker_set_volume': '调节音量', 'self_screen_show_text': '屏幕显示文字',
    'self_camera_preview': '拍照预览', 'self_set_language': '切换语言', 'self_enter_standby': '待机',
    'self_get_device_status': '查询设备状态', 'self_laser_control': '激光控制',
    'self_ble_remote_control': '蓝牙遥控', 'self_arm_calibrate': '机械臂标定',
}


def canonical(name):
    return name.replace('.', '_')


def validate_arguments(arguments, schema):
    """Validate the flat device schemas, plus nested JSON primitives if supplied."""
    kind = schema.get('type')
    checks = {'object': lambda x: isinstance(x, dict), 'array': lambda x: isinstance(x, list),
              'integer': lambda x: type(x) is int, 'number': lambda x: type(x) in (int, float),
              'string': lambda x: isinstance(x, str), 'boolean': lambda x: type(x) is bool,
              'null': lambda x: x is None}
    if kind in checks and not checks[kind](arguments):
        raise ValueError('Tool argument type does not match schema')
    if 'enum' in schema and arguments not in schema['enum']:
        raise ValueError('Tool argument is not in enum')
    if type(arguments) in (int, float):
        import math
        if not math.isfinite(arguments) or arguments < schema.get('minimum', -float('inf')) or arguments > schema.get('maximum', float('inf')):
            raise ValueError('Tool argument is outside the allowed range')
    if isinstance(arguments, dict):
        if any(k not in arguments for k in schema.get('required', [])):
            raise ValueError('Required tool argument is missing')
        properties = schema.get('properties')
        if properties is not None:
            if any(k not in properties for k in arguments):
                raise ValueError('Unknown tool argument')
            for key, value in arguments.items():
                validate_arguments(value, properties[key])
    if isinstance(arguments, list) and 'items' in schema:
        for value in arguments:
            validate_arguments(value, schema['items'])


def number(text):
    if text.isascii() and text.isdigit():
        return int(text)
    digits = dict(zip('零〇一二两三四五六七八九', (0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9)))
    if not any(c in text for c in '十百'):
        return int(''.join(str(digits[c]) for c in text))
    simplified = text.replace('零', '').replace('〇', '')
    match = re.fullmatch(r'(?:(一|二|两|三|四|五|六|七|八|九)百)?(?:(一|二|两|三|四|五|六|七|八|九)?十)?(一|二|两|三|四|五|六|七|八|九)?', simplified)
    if not match or not simplified:
        raise ValueError('Ambiguous number')
    hundred, ten, unit = match.groups()
    return (digits[hundred] * 100 if hundred else 0) + ((digits[ten] if ten else 1) * 10 if '十' in simplified else 0) + (digits[unit] if unit else 0)


def command(text):
    # Full matches only. Quoted, hypothetical, multi-action or contextual phrases
    # never become a shortcut merely because they contain a command substring.
    if '?' in text or '？' in text or re.search(r'\d\s+\d', text):
        return None
    text = re.sub(r'\s+', '', text).strip('。！!')
    text = re.sub(r'^(?:请你|请|麻烦你|麻烦|帮我)', '', text, count=1)
    simple = {
        r'(?:鞠躬|鞠个躬|行礼|行个礼|给我行个礼)': 'bow',
        r'(?:点头|点一下头|点个头)': 'node', r'(?:摇头|摇一下头)': 'shake',
        r'(?:伸懒腰|伸个懒腰)': 'stretch',
        r'(?:停止(?:当前|正在做的)?动作|别动了|别动了[，,]停止正在做的动作)': 'stop',
        r'(?:结束示教(?:录制)?(?:并保存)?(?:[，,]不要回放)?)': 'teach_stop',
        r'(?:回放(?:刚才保存的)?示教轨迹|回放示教)': 'teach_play',
    }
    for pattern, action in simple.items():
        if re.fullmatch(pattern, text):
            return 'self_arm_' + action, {}
    performances = {'鞠躬': 'bow', '点头': 'node', '摇头': 'shake', '伸懒腰': 'stretch',
                    '害羞': 'shy', '撒娇': 'coquetry', '卖萌': 'coquetry', '道歉': 'apology',
                    '装死': 'feign_death', '摇尾巴': 'wag_tail'}
    match = re.fullmatch(r'(?:表演(?:一下|一个)?|做(?:一下|一个)?|来个)(鞠躬|点头|摇头|伸懒腰|害羞|撒娇|卖萌|道歉|装死|摇尾巴)(?:动作|表演)?', text)
    if match:
        return 'self_arm_' + performances[match[1]], {}
    if re.fullmatch(r'(?:退出对话|结束对话|进入待机|先不聊了|不聊了|再见|去休息吧)', text):
        return 'self_enter_standby', {}
    match = re.fullmatch(r'(打开|开启|关闭|关掉)空闲微动', text)
    if match:
        return 'self_arm_idle_motion', {'enable': int(match[1] in ('打开', '开启'))}
    match = re.fullmatch(rf'(?:把)?(?:头部|头)?(?:朝|向|往)(左|右)(?:旋转|转)({NUMBER})度', text)
    if match:
        return 'self_arm_yaw', {'yaw': number(match[2]) * (1 if match[1] == '左' else -1)}
    match = re.fullmatch(rf'(?:把)?(?:头部|头)?(?:向|往)(上|下)(?:抬|转|旋转)({NUMBER})度', text)
    if match:
        return 'self_arm_pitch', {'pitch': number(match[2]) * (-1 if match[1] == '上' else 1)}
    match = re.fullmatch(rf'(?:把头)?(抬高|抬头|低头)({NUMBER})度', text)
    if match:
        return 'self_arm_pitch', {'pitch': number(match[2]) * (1 if match[1] == '低头' else -1)}
    match = re.fullmatch(rf'(?:向|往)(左|右)歪头({NUMBER})度', text)
    if match:
        return 'self_arm_roll', {'roll': number(match[2]) * (1 if match[1] == '左' else -1)}
    match = re.fullmatch(rf'(?:把)?(?:头部|头)?(?:向|往)(左|右)(?:平移|移动)({NUMBER})厘米', text)
    if match:
        return 'self_arm_y', {'y': number(match[2]) * (1 if match[1] == '左' else -1)}
    match = re.fullmatch(rf'(?:把)?(?:头部|头)?(?:向|往)(前|后|上|下)(?:平移|移动)({NUMBER})厘米', text)
    if match:
        axis = 'x' if match[1] in ('前', '后') else 'z'
        return 'self_arm_' + axis, {axis: number(match[2]) * (1 if match[1] in ('前', '上') else -1)}
    return None


def call_event(name, arguments):
    return {'tool_calls': [{'index': 0, 'id': 'call_local_' + uuid.uuid4().hex,
                           'type': 'function', 'function': {'name': name,
                           'arguments': json.dumps(arguments, ensure_ascii=False)}}]}


def prepare_request(body):
    body = copy.deepcopy(body)
    messages = body.get('messages', [])
    if not isinstance(messages, list) or not messages or len(messages) > 80:
        raise ValueError('messages must contain between 1 and 80 entries')
    if any(not isinstance(m, dict) or not isinstance(m.get('content', ''), (str, type(None))) for m in messages):
        raise ValueError('This deployment accepts text messages only')
    body['tools'] = [t for t in (body.get('tools') or [])
                     if canonical(t.get('function', {}).get('name', '')) != 'self_camera_describe_view']
    tools = {canonical(t['function']['name']): t['function'] for t in body['tools']}
    robot = any(name.startswith('self_arm_') for name in tools)
    route, immediate = 'generic', None
    if robot:
        replaced = False
        for message in messages:
            if message.get('role') == 'system' and isinstance(message.get('content'), str):
                if BUILTIN in message['content']:
                    message['content'] = message['content'].replace(BUILTIN, COMPACT)
                    replaced = True
        if not replaced:
            messages.insert(0, {'role': 'system', 'content': COMPACT})
        last = messages[-1]
        text = last.get('content') or ''
        if last.get('role') == 'user':
            try:
                parsed = command(text)
            except (ValueError, KeyError):
                parsed = None
            if parsed and parsed[0] in tools:
                name, arguments = parsed
                function = tools[name]
                try:
                    validate_arguments(arguments, function.get('parameters', {}))
                except ValueError:
                    labels = {'yaw': '左右旋转角度', 'pitch': '上下旋转角度', 'roll': '歪头角度',
                              'x': '前后平移距离', 'y': '左右平移距离', 'z': '上下平移距离'}
                    limits = '，'.join(f'{labels.get(key, "数值")}范围为{rule["minimum"]}到{rule["maximum"]}{"厘米" if key in ("x", "y", "z") else "度"}'
                                      for key, rule in function.get('parameters', {}).get('properties', {}).items()
                                      if 'minimum' in rule and 'maximum' in rule)
                    immediate = [{'content': f'这个数值超出范围。{limits}，请换一个范围内的数值。'}]
                    route = 'range-clarification'
                else:
                    immediate = [call_event(function['name'], arguments)]
                    route = 'exact-command'
            elif DENIAL.search(text) or CAPABILITY.fullmatch(text.strip()) or not ACTION_WORDS.search(text):
                body['tools'] = []
                route = 'chat'
            else:
                route = 'tool-inference'
        elif last.get('role') == 'tool':
            previous = next((m for m in reversed(messages[:-1]) if m.get('role') == 'assistant'), {})
            names = {canonical(c.get('function', {}).get('name', '')) for c in previous.get('tool_calls', [])}
            # A read-only status lookup can be a prerequisite (e.g. volume).
            # An accepted/failed motion must never trigger an automatic retry.
            readonly = {'self_get_device_status', 'self_arm_action_status', 'self_arm_teach_status'}
            if names and names <= readonly:
                route = 'tool-result-inference'
            else:
                body['tools'] = []
                route = 'tool-result'
        if not body['tools']:
            capabilities = '、'.join(label for name, label in CAPABILITIES.items() if name in tools)
            messages.insert(1, {'role': 'system', 'content': '设备已提供的能力：' + capabilities + '。本轮只作口头回答，不执行操作。'})
    body['_local_route'] = route
    return body, immediate
