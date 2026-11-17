# PC 与设备接口

PC 只生成工具调用，不主动向设备发电机命令。设备上传本轮可用工具及会话，接收调用后由设备固件检查和执行。测试中的工具清单是兼容性样本，实机的工具名、参数范围和动作语义仍需对照所用固件确认。

| PC 路径 | 作用 | 鉴权 |
| --- | --- | --- |
| `GET /health` | 就绪状态及预期后端；不证明 NPU 硬件执行 | 不需要；仅公开基本服务元数据 |
| `GET /v1/models` | 本地模型标识 | `Authorization: Bearer <api_key>` |
| `POST /v1/chat/completions` | 部分 OpenAI 兼容聊天/工具格式，支持 SSE | 同上 |
| `POST /v1/audio/speech` | 文本转 WAV，或 `response_format=pcm` | 同上 |
| `POST /local/asr` | 原始 PCM 转文字 | 同上 |
| `WS /api-ws/v1/realtime` | 流式识别，`session.update`、音频 append/commit/clear | 握手请求头携带服务密钥 |
| `WS /api-ws/v1/inference/` | 双向 TTS，run-task/continue-task/finish-task | 同上 |
| `POST /local/shutdown` | 退出本机服务 | 服务密钥且连接源必须为回环地址 |

音频为 16 kHz、单声道、16 位小端 PCM；HTTP ASR 最长 30 秒。协议字段和用例见 `tests/integration.py`。这些接口只实现本设备所需子集，不保证与所有 OpenAI 客户端功能兼容。

设备的 `POST /mcp` 是另一条控制入口：JSON-RPC 的 initialize、tools/list、tools/call 等都应先验证 **robot_api_key**。公开后端没有通用设备控制客户端，调用者需自行安全接入。示例测试不会调用此入口。

## 动作边界

- 示例位移范围：x ±3 cm，y ±2 cm，z ±5 cm；yaw ±60°，pitch/roll ±30°，均为整数。
- x 正向前、y 正向左、z 正向上；yaw 正向左转、pitch 正向低头、roll 正向左歪。
- `self_arm_node` 保留已有协议拼写，不改成 `nod`。
- `accepted` 不代表已完成。执行状态应由设备反馈，失败或忙碌时不自动重试。
- 保存示教不授权回放；停止后归位会产生运动。安全限位、急停和工作区域隔离属于设备层责任。

应用会拒绝不在当前工具表中的调用，校验参数并限制单轮一个调用。简单完整指令可由规则生成调用；其他动作请求进入模型。否定、引用、假设的识别是启发式逻辑，并非无误的语义或安全判断。需要可靠控制时，应在设备层保留独立许可、限位和状态校验。
