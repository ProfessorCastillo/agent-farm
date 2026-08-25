# Ollama Participant Model Inventory

Generated: 2026-08-22T21:23:54+00:00

> Native context is the model metadata limit. It is not necessarily the context Ollama allocates when the model runs.

| Model | ID | Disk size | Architecture | Parameters | Quant | Native context | num_ctx override | Experts | Capabilities |
|---|---|---|---|---|---|---|---|---|---|
| ornith-1.5:9b | e5df7dcdd8a2 | 6.6 GB | qwen35 | 9.0B | Q4_K_M | 262,144 | — | Dense | tools, thinking, completion, vision |
| ornith-1.5:35b | 9f3b89b25219 | 22 GB | qwen35moe | 35.5B | Q4_K_M | 262,144 | — | 256 / 8 active | tools, thinking, completion, vision |
| nemotron-3.5-lightning:30b | e7a64ff15fb1 | 25 GB | nemotron_h_moe | 32.9B | Q4_K_M | 1,048,576 | — | 128 / 6 active | completion, tools, thinking |
| muse-glimmer:30b | de878ce33ad8 | 18 GB | muse-glimmer | 27.9B | Q4_K_M | 131,072 | — | Dense | completion, vision, tools, thinking |
| qwen3.8:27b | 22130167c4c2 | 17 GB | qwen35 | 27.3B | Q4_K_M | 262,144 | — | Dense | completion, vision, tools, thinking |
| qwen3.5:9b | 6488c96fa5fa | 6.6 GB | qwen35 | 9.7B | Q4_K_M | 262,144 | — | Dense | completion, vision, tools, thinking |
| qwen3.6:35b | 07d35212591f | 23 GB | qwen35moe | 36.0B | Q4_K_M | 262,144 | — | 256 / 8 active | completion, vision, tools, thinking |
| gemma4:31b | 6316f0629137 | 19 GB | gemma4 | 31.3B | Q4_K_M | 262,144 | — | Dense | completion, vision, tools, thinking |
| gemma4:26b | 5571076f3d70 | 17 GB | gemma4 | 25.8B | Q4_K_M | 262,144 | — | 128 / 8 active | completion, vision, tools, thinking |
| qwen3.5:27b | 7653528ba5cb | 17 GB | qwen35 | 27.8B | Q4_K_M | 262,144 | — | Dense | completion, vision, tools, thinking |
| qwen3.5:35b | 4af949f8bdf0 | 23 GB | qwen35moe | 36.0B | Q4_K_M | 262,144 | — | 256 / 8 active | completion, vision, tools, thinking |
| gpt-oss:20b-131k | 4d2f07cece89 | 13 GB | gptoss | 20.9B | MXFP4 | 131,072 | 131,072 | 32 / 4 active | completion, tools, thinking |
| ministral-3:14b | 4760c35aeb9d | 9.1 GB | mistral3 | 13.9B | Q4_K_M | 262,144 | — | Dense | completion, vision, tools |
| ministral-3:8b | 1922accd5827 | 6.0 GB | mistral3 | 8.9B | Q4_K_M | 262,144 | — | Dense | completion, vision, tools |
| devstral-small-2:24b | 24277f07f62d | 15 GB | mistral3 | 24.0B | Q4_K_M | 393,216 | — | Dense | completion, vision, tools |
| nemotron-3-nano:30b | b725f1117407 | 24 GB | nemotron_h_moe | 31.6B | Q4_K_M | 1,048,576 | — | 128 / 6 active | completion, tools, thinking |
