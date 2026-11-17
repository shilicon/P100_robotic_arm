# 模型来源与下载

模型与编译缓存不纳入 Git。`scripts/models.py` 只从固定版本下载，并逐文件校验大小和摘要。大文件使用上游 SHA-256，普通 Git 文件使用 Git blob SHA-1（含 `blob <size>\0` 前缀）；Silero 文件使用 SHA-256。修改清单意味着修改信任来源，需要重新审核。

| 本地目录/文件 | 来源与固定版本 | 大小 |
| --- | --- | --- |
| `models/qwen3-8b-npu-4k/` | [amd/Qwen3-8B_rai_1.8.0_npu_4K](https://huggingface.co/amd/Qwen3-8B_rai_1.8.0_npu_4K/tree/21b7692377beeba88303a7aa59d32bffed7feff3) | 95 个文件，10,911,194,640 字节 |
| `models/sensevoice/` | [SenseVoice sherpa-onnx int8](https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/tree/2365baeacb507f821a0c8120fcee3d484dba7a07) | 模型、词表、README、LICENSE 共 239,549,910 字节 |
| `models/silero_vad.onnx`、`models/silero/LICENSE` | [Silero 固定提交](https://github.com/snakers4/silero-vad/tree/bfdc0193023f121ea5b3cc7b176dbed570a68a59) | 共 2,328,599 字节 |

Qwen 模型卡声明原模型为 Apache-2.0，AMD 修改为 MIT，并要求参阅 [AMD Ryzen AI 1.8.0 Models 第三方通知](https://account.amd.com/content/dam/account/en/licenses/download/ryzen-ai-1-8-0-models-tpn-license.pdf)。脚本保留仓库的 README/LICENSE 和推理所需的编译上下文等文件，不只下载 ONNX。

SenseVoice 模型仓库的 LICENSE 指向 [FunASR 许可说明](https://github.com/modelscope/FunASR?tab=readme-ov-file#license)。模型使用、商用和再分发条件需要按该说明及原模型条款确认；本项目不将其统一标为 Apache 或 MIT。`--accept-model-terms` 仅表示下载者已阅读并接受适用条款，不产生新的授权。

```sh
python scripts/models.py list
python scripts/models.py download --accept-model-terms
python scripts/models.py verify
# 也可只下载一组：
python scripts/models.py download --model silero --accept-model-terms
```

下载写入临时文件，完整校验后才替换目标文件。中断后再次运行会跳过已校验的文件，未完成的单个文件从头下载。默认模型需要约 11.15 GB，临时文件和环境另占空间，请预留至少 25 GB 可用空间。

Qwen 上游通用配置中的最大位置长度不代表本部署可用上下文。应用将上下文上限限制为 4096，并为输出预留空间。更换模型需要同时确认运行时、词表、工具模板、硬件和上下文限制。

文件校验成功只证明下载与固定版本一致，不证明模型能在指定“P100”硬件上运行，也不能证明实际使用了 NPU。
