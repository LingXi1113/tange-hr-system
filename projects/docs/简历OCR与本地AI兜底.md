# 简历 OCR 与本地 AI 兜底

上传 PDF、DOCX、JPG 或 PNG 后，系统先提取原生文字。图片及原生文字不足的 PDF 会调用本地 RapidOCR；规则解析缺字段或置信度较低时，再调用配置的大模型补全。原始附件和人工核对入口继续保留。

页面展示解析方式、启发式置信度和核对提醒。置信度是字段完整度及 OCR 分数的综合提示，不代表统计准确率。AI 失败时保留规则结果并提示核对。

## 当前电脑

- Ollama：`D:\hr-ats-ocr\Ollama\ollama.exe`
- 模型目录：`D:\hr-ats-ocr\models`，已设置用户环境变量 `OLLAMA_MODELS`。
- 模型：`qwen3:1.7b`。
- 从 backend 目录执行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\start-local-ai.ps1` 启动启用本地 AI 的后端，运行前应关闭旧后端。
- 本地 API：`http://127.0.0.1:11434/v1`，无需 API Key。
- 本地模型使用 CPU 推理，速度受简历长度和电脑负载影响。

## 部署配置

后端读取进程环境变量，不自动加载 `.env`：

```text
HRATS_RESUME_AI_ENABLED=1
HRATS_RESUME_AI_BASE_URL=http://127.0.0.1:11434/v1
HRATS_RESUME_AI_MODEL=qwen3:1.7b
HRATS_RESUME_AI_TIMEOUT=120
```

以后换为外部兼容服务时，替换地址、模型并通过部署环境注入 `HRATS_RESUME_AI_API_KEY`，不要将真实密钥提交到代码仓库。

## 验证

简历相关测试：`python -m pytest -q -k resume`。

本地真实联调：先设置上述变量，再执行 `python smoke_resume_local_ai.py`。该脚本用虚构资料生成 Word、图片和扫描 PDF，验证 OCR、AI 提取及最终合并，不写入候选人数据库。

