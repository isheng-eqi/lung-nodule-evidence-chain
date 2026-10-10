# 提交包文件清单

> 生成时间：2026-10-10 21:48
> 文件总数：**130**　总大小：**4.8 MB**

---

# 一、目录结构与用途

| 目录 | 文件数 | 大小 | 用途 |
|---|---|---|---|
| `(根目录)` | 6 | 53.5 KB | — |
| `01_开发设计文档` | 26 | 2.9 MB | 初赛主材料：开发设计文档 Word + 调用关系图 + 验证记录 + 界面截图 |
| `02_代码与本体` | 44 | 686.2 KB | 代码与本体：OWL 本体、知识图谱服务、MCP Server、Skill、评测、脚本、工具 |
| `03_验证与数据` | 39 | 724.9 KB | 验证与数据：自测评测集与报告、批量验证记录、结构化指标、资产注册表 |
| `04_参考资料` | 10 | 290.3 KB | 参考资料清单（数据来源、标准体系、合规依据） |
| `05_答辩材料` | 5 | 255.4 KB | 国赛准备：中英答辩 PPT、答辩框架、英文口语稿、附加分调研 |

---

# 二、逐文件清单

## (根目录)

| 文件 | 大小 | 用途 | SHA256（前 16 位） |
|---|---|---|---|
| `.gitignore` | 559 B |  | `09c820a3098f252d` |
| `00_提交包说明.md` | 21.3 KB | 提交包总说明：目录结构、官方要求对照、诚实声明 | `373534a2c3ceb156` |
| `LICENSE` | 11.6 KB |  | `7e97de26c7172936` |
| `README.md` | 5.9 KB |  | `fe22d24c3c7b5589` |
| `THIRD_PARTY_NOTICES.md` | 5.0 KB |  | `0774ec6eb8197125` |
| `一键复现指南.md` | 9.1 KB |  | `e570d4e971cbbce4` |

## 01_开发设计文档

| 文件 | 大小 | 用途 | SHA256（前 16 位） |
|---|---|---|---|
| `01_开发设计文档/Skill骨架跨行业复用验证.md` | 9.3 KB |  | `e2f3ea902707bb9f` |
| `01_开发设计文档/图文类资产处理验证记录.md` | 11.0 KB | VLM 识别链路验证（图文类资产） | `f7183ca4a83188be` |
| `01_开发设计文档/外部复核指南.md` | 7.5 KB |  | `7e0883abcc1c97be` |
| `01_开发设计文档/对照实验_裸模型vs本系统.md` | 10.2 KB |  | `f6217dea36cf8d94` |
| `01_开发设计文档/开发设计文档_final.docx` | 1.2 MB | ★ 初赛主文档（Word） | `7dc7b18f541874a7` |
| `01_开发设计文档/开发设计文档_源文件.md` | 166.7 KB | 主文档的 Markdown 源文件（便于修改后重新生成） | `b7f779eae0aebb24` |
| `01_开发设计文档/待排查_智能体未调用kg工具.md` | 6.7 KB |  | `e1ab00aaecf8f1ee` |
| `01_开发设计文档/拒答追问机制验证记录.md` | 9.0 KB | 三层拒答机制的界面验证 | `84939bd092100d5e` |
| `01_开发设计文档/本体完备性审计与成长实验.md` | 11.6 KB |  | `ccd44e6c9f8b1ffe` |
| `01_开发设计文档/消融实验_检索与图谱的必要性.md` | 9.7 KB |  | `fa49a577f70ab5c7` |
| `01_开发设计文档/界面截图/01_智能体配置页.png` | 136.3 KB |  | `ad6f000df8c5786c` |
| `01_开发设计文档/界面截图/02_工具与技能_MCP挂载.png` | 102.0 KB |  | `9398e81a913e28b5` |
| `01_开发设计文档/界面截图/02_工具与技能_完整配置.png` | 121.4 KB |  | `2bba57567cd43b14` |
| `01_开发设计文档/界面截图/03_调试问答_完整证据.png` | 186.8 KB |  | `2e78dd25b59ffdb5` |
| `01_开发设计文档/界面截图/04_调试问答_回答开头.png` | 182.6 KB |  | `94388bc4e9fad1f9` |
| `01_开发设计文档/界面截图/05_拒答追问_交互表单.png` | 199.1 KB |  | `bdf4517e6fd450f9` |
| `01_开发设计文档/界面截图/06_拒答追问_填写表单.png` | 199.3 KB |  | `ad0245c5f2480b72` |
| `01_开发设计文档/界面截图/07_补充信息后作答.png` | 237.9 KB |  | `11da96f5dc77b16f` |
| `01_开发设计文档/界面操作证据.md` | 8.2 KB | 8 张界面截图的清单与逐张说明 | `cc02fc505636f0f9` |
| `01_开发设计文档/真实脱敏数据集评测.md` | 8.0 KB |  | `5388cbdecec806e9` |
| `01_开发设计文档/端到端运行验证记录.md` | 10.4 KB | 检索-推理双驱动的完整证据（工具调用序列） | `5844165cc5dfa064` |
| `01_开发设计文档/评测集金标准核对表.md` | 10.6 KB |  | `3675ad3a9e448308` |
| `01_开发设计文档/调用关系图.json` | 974 B | 平台导出的调用关系原始数据 | `9e34ce11b4280fd3` |
| `01_开发设计文档/调用关系图.md` | 10.9 KB | ★ 官方要求的调用关系图 | `c3a4878b246ad287` |
| `01_开发设计文档/跨文档推理的实现与验证.md` | 9.1 KB |  | `e75af3b8266bc093` |
| `01_开发设计文档/运行态知识边界.md` | 9.9 KB |  | `4e1449fca80cdd52` |

## 02_代码与本体

| 文件 | 大小 | 用途 | SHA256（前 16 位） |
|---|---|---|---|
| `02_代码与本体/eval/ablation_rag_vs_kg.py` | 11.4 KB |  | `f8d84cc7dea76f40` |
| `02_代码与本体/eval/ablation_summary.py` | 9.6 KB |  | `341f277f0c29acdf` |
| `02_代码与本体/eval/agent_eval_runner.py` | 13.2 KB |  | `0ff32100e8c4a22e` |
| `02_代码与本体/eval/agent_eval_strict.py` | 11.6 KB |  | `6a1c9a34bcf3f696` |
| `02_代码与本体/eval/build_evalset.py` | 22.2 KB | 自测评测集生成器（68 条 / 六类） | `cb34d47e339f8ca6` |
| `02_代码与本体/eval/compare_raw_vs_system.py` | 9.9 KB |  | `542ac3c582ddb08e` |
| `02_代码与本体/eval/eval_runner.py` | 9.7 KB | 自测评测执行器 | `1f53d11a570eca97` |
| `02_代码与本体/eval/medrep_bench_eval.py` | 10.6 KB |  | `891d71a63e31519a` |
| `02_代码与本体/kg-service/asset_activation_path.py` | 22.4 KB |  | `9f4193c6ba1947c1` |
| `02_代码与本体/kg-service/asset_identifier.py` | 21.1 KB | 六维数据资产标识 | `e1f4d258a84fe0d5` |
| `02_代码与本体/kg-service/build_clause_table.py` | 17.0 KB | 条款结构化表格生成 | `eb5b4e760963d7f8` |
| `02_代码与本体/kg-service/clean_corpus.py` | 11.2 KB | 语料清洗器（括号配对 JSON 剥离） | `e3d756a13cb9f5ef` |
| `02_代码与本体/kg-service/imaging_pipeline.py` | 14.1 KB | 图文类资产处理流水线（VLM → 推理） | `4264f4f9788baf4a` |
| `02_代码与本体/kg-service/kg_reasoning_service.py` | 20.3 KB | 知识图谱推理服务（三元组 + 多跳） | `07fce9e2e4902cfd` |
| `02_代码与本体/kg-service/migration_cost.py` | 12.6 KB |  | `416750da679bf535` |
| `02_代码与本体/kg-service/ontology_builder.py` | 35.9 KB | ★ 本体半自动化构建算法（三层流水线） | `a79f976c2c7f20a7` |
| `02_代码与本体/kg-service/ontology_coverage_audit.py` | 7.2 KB |  | `8fc87f8b0f6a1b53` |
| `02_代码与本体/kg-service/ontology_export.py` | 12.7 KB | OWL/TTL 导出器 | `3fe2aed438a858d1` |
| `02_代码与本体/kg-service/ontology_growth_experiment.py` | 12.2 KB |  | `bac1397a7b4376dc` |
| `02_代码与本体/kg-service/ontology_wiring_audit.py` | 7.6 KB |  | `fdfc1bb3067745c8` |
| `02_代码与本体/kg-service/workflow_template.py` | 56.7 KB | ★ 可复用工作流模板（含迁移验证） | `714d0e271eece957` |
| `02_代码与本体/mcp-server/README.md` | 9.7 KB |  | `4dd7cae156cd31e2` |
| `02_代码与本体/mcp-server/kg_mcp_server.py` | 60.9 KB | ★ 自研 MCP Server（工具数见下） | `60ec1db8b0abcf2c` |
| `02_代码与本体/mcp-server/mcp-ctl.sh` | 4.1 KB | MCP 服务启停与自检 | `5deca66e4841a0f1` |
| `02_代码与本体/mcp-server/mcp_client_test.py` | 1.4 KB |  | `77f00c8adbfb442d` |
| `02_代码与本体/ontology/generated/lung_nodule_ontology_pipeline.ttl` | 19.8 KB | OWL 本体（流水线版，可从构建流程重现） | `93b43d6ad60814f8` |
| `02_代码与本体/ontology/lung_nodule_ontology.ttl` | 35.8 KB | ★ OWL 本体（增强版，57 类） | `728dd77b14e8f061` |
| `02_代码与本体/ontology/lung_nodule_ontology_v13_62classes.ttl` | 21.9 KB |  | `2a946651eaf30aed` |
| `02_代码与本体/scripts/batch_e2e.sh` | 3.0 KB | 8 场景批量验证脚本 | `deff3b073906853a` |
| `02_代码与本体/scripts/e2e_call.sh` | 2.0 KB | 单次端到端调用脚本 | `00eb00c848d63e15` |
| `02_代码与本体/skill/lung-nodule-decision/SKILL.md` | 7.3 KB | ★ Skill 定义（三层编排） | `bf72ff729e9a2924` |
| `02_代码与本体/skill/lung-nodule-decision/config/schema.yaml` | 1.8 KB | Skill 参数配置（7 个参数） | `2a6c721f1d2afe86` |
| `02_代码与本体/skill/skill_template.py` | 19.3 KB |  | `1d4f3c10353a9d4c` |
| `02_代码与本体/tools/build_consequence.py` | 4.1 KB |  | `845d97f2d642ae46` |
| `02_代码与本体/tools/build_defense_ppt.py` | 40.4 KB | 中文答辩 PPT 生成器 | `78a07feca69b2b66` |
| `02_代码与本体/tools/build_defense_ppt_en.py` | 41.6 KB | 英文答辩 PPT 生成器 | `9837c48043c9049e` |
| `02_代码与本体/tools/build_net_gain.py` | 3.9 KB |  | `9e2da6ea49850ca9` |
| `02_代码与本体/tools/check_package.py` | 9.4 KB | 提交包一致性检查器 | `fb7ac3972a6f9eb7` |
| `02_代码与本体/tools/consistency_scan.py` | 11.2 KB |  | `6b0c8a3058e13942` |
| `02_代码与本体/tools/ingest_knowledge_base.py` | 6.8 KB |  | `a4c0096cbf51ec06` |
| `02_代码与本体/tools/inject_metrics.py` | 8.7 KB |  | `4289faef46adc39c` |
| `02_代码与本体/tools/md2docx.py` | 10.1 KB | Markdown → Word 转换器 | `15831de2b5a4a01e` |
| `02_代码与本体/tools/parse_agent_response.py` | 8.8 KB | 智能体响应解析器 | `54ddd3857f11c793` |
| `02_代码与本体/tools/verify_evidence.py` | 5.1 KB |  | `4ae7be472d551fd8` |

## 03_验证与数据

| 文件 | 大小 | 用途 | SHA256（前 16 位） |
|---|---|---|---|
| `03_验证与数据/clauses_table.csv` | 6.4 KB | 条款结构化表格（18 × 14） | `5c0e22c8f66bb51e` |
| `03_验证与数据/clauses_table.md` | 7.3 KB |  | `bff15980e86be762` |
| `03_验证与数据/coverage_audit.json` | 15.0 KB |  | `1c65a19233ef25ea` |
| `03_验证与数据/coverage_audit_v13.json` | 12.2 KB |  | `7cba0afe9545f870` |
| `03_验证与数据/growth_report.json` | 5.3 KB |  | `e0d27e30f1cb1620` |
| `03_验证与数据/skill_migration_report.json` | 1.7 KB |  | `673cdd67722e99b1` |
| `03_验证与数据/四份文档构建报告.json` | 1.4 KB |  | `ebffea081e5e1522` |
| `03_验证与数据/图文识别结果.json` | 5.4 KB | VLM 识别 + 推理 + 资产标识的完整结果 | `6c2b58ba22df45fa` |
| `03_验证与数据/多行业迁移验证报告.json` | 7.5 KB | ★ 多行业迁移验证（医疗 + 金融） | `ca9c00f575a4bb9c` |
| `03_验证与数据/对照实验_裸模型原始输出.json` | 14.7 KB |  | `7361dca11be58e19` |
| `03_验证与数据/影像报告样例.png` | 141.6 KB | 图文类资产样例（按标准格式构造） | `b9620f6e3b0cb65a` |
| `03_验证与数据/智能体层端到端评测.json` | 218.1 KB |  | `5c589fde7dab0e76` |
| `03_验证与数据/智能体层端到端评测_严格判据.json` | 22.0 KB |  | `cc2402d3c40778e3` |
| `03_验证与数据/智能体层端到端评测_重复采样.json` | 30.2 KB |  | `e84ba46b00217971` |
| `03_验证与数据/本体接线审计_医疗.json` | 3.5 KB |  | `397dfb0587f2398b` |
| `03_验证与数据/本体接线审计_金融.json` | 4.8 KB |  | `7adf9eb808d1a0b3` |
| `03_验证与数据/本体构建质量报告.json` | 1007 B | 本体构建的量化指标 | `8defa6d3241a297c` |
| `03_验证与数据/消融实验_RAG基线原始输出.json` | 8.1 KB |  | `487ac946718d27c5` |
| `03_验证与数据/消融实验_三配置对照.json` | 9.9 KB |  | `cf61480ba83df961` |
| `03_验证与数据/消融实验_净收益量化.json` | 1.8 KB |  | `cf819a2cda4c0c8e` |
| `03_验证与数据/消融实验_后果对照.json` | 3.9 KB |  | `664b6983e42a83d0` |
| `03_验证与数据/真实脱敏数据集评测_MedRepBench.json` | 9.4 KB |  | `898c522d33173bf5` |
| `03_验证与数据/知识库入库报告.json` | 1.5 KB |  | `04cdfa94113ed135` |
| `03_验证与数据/端到端批量验证记录.md` | 36.2 KB | 8 场景批量验证记录 | `236bdb486d6621ee` |
| `03_验证与数据/端到端问答记录.json` | 6.1 KB |  | `d2f25631b52738a7` |
| `03_验证与数据/端到端问答记录.md` | 4.2 KB |  | `cac707442087dc66` |
| `03_验证与数据/结构化指标/S1.json` | 5.7 KB |  | `164bf3afa5277590` |
| `03_验证与数据/结构化指标/S2.json` | 5.4 KB |  | `25d62b67779ab940` |
| `03_验证与数据/结构化指标/S3.json` | 3.9 KB |  | `32682038c58bec89` |
| `03_验证与数据/结构化指标/S4.json` | 3.7 KB |  | `70accd67f1b7541e` |
| `03_验证与数据/结构化指标/S5.json` | 7.1 KB |  | `7add0acb7106a937` |
| `03_验证与数据/结构化指标/S6.json` | 1.9 KB |  | `81c89a660530a10b` |
| `03_验证与数据/结构化指标/S7.json` | 2.3 KB |  | `242d6fca87196189` |
| `03_验证与数据/结构化指标/S8.json` | 7.0 KB |  | `ae8e18a0e2e9273c` |
| `03_验证与数据/自测报告_58条.json` | 40.0 KB |  | `10ec6500f7c1ce6c` |
| `03_验证与数据/自测评测集_58条.json` | 31.3 KB |  | `19e43e3e60f93235` |
| `03_验证与数据/资产标识注册表.json` | 13.0 KB | 三种模态的数据资产清单 | `3631f96b6832876f` |
| `03_验证与数据/资产激活路径台账.json` | 17.1 KB |  | `2848cf4980e84f9f` |
| `03_验证与数据/迁移成本量化报告.json` | 7.2 KB |  | `5933fddb68607e41` |

## 04_参考资料

| 文件 | 大小 | 用途 | SHA256（前 16 位） |
|---|---|---|---|
| `04_参考资料/原文_2024共识_全文.txt` | 48.7 KB |  | `398d44017edb2f46` |
| `04_参考资料/原文_固定资产贷款管理办法2024_清洗后.txt` | 21.3 KB |  | `ab5cfb4f03b9b73f` |
| `04_参考资料/原文_特种设备安全法_清洗后.txt` | 47.2 KB |  | `b80abbcc4cf4b34b` |
| `04_参考资料/参考资料清单.md` | 3.8 KB |  | `f1b47dc58a4484ca` |
| `04_参考资料/筛查指南2023_结构化版.txt` | 20.5 KB |  | `6a605999a08e56f5` |
| `04_参考资料/筛查指南2025_全文.txt` | 24.5 KB |  | `5218b24686a60abe` |
| `04_参考资料/语料_2024共识_清洗后.txt` | 48.5 KB |  | `7b66aa3719ea7159` |
| `04_参考资料/语料_2025共识_清洗后.txt` | 30.9 KB |  | `ab16d801f389a186` |
| `04_参考资料/语料_筛查指南2023_清洗后.txt` | 20.5 KB |  | `8b793dc90108750b` |
| `04_参考资料/语料_筛查指南2025_清洗后.txt` | 24.4 KB |  | `c74d49e7d69e8be1` |

## 05_答辩材料

| 文件 | 大小 | 用途 | SHA256（前 16 位） |
|---|---|---|---|
| `05_答辩材料/DefenseDeck_EN.pptx` | 95.9 KB | 英文答辩 PPT（20 页） | `be540cbc4880f358` |
| `05_答辩材料/English_Defense_Speaking_Notes.md` | 23.4 KB | 英文口语稿 + 10 个预设问答 | `8d8f44c54e7ba187` |
| `05_答辩材料/国赛答辩PPT.pptx` | 99.5 KB | 中文答辩 PPT（20 页） | `2df0cbfeaf66e720` |
| `05_答辩材料/国赛答辩框架.md` | 28.4 KB | 答辩框架 + 10 个预设问答 | `7c910636b784d548` |
| `05_答辩材料/附加分调研_真实脱敏数据集.md` | 8.2 KB | 真实脱敏数据集调研结论 | `d742281761d167da` |

---

# 三、校验方式

```bash
# 校验全部文件是否与清单一致
sha256sum -c CHECKSUMS.sha256

# 或仅查看某个文件的哈希
sha256sum 01_开发设计文档/开发设计文档_final.docx
```

> 完整哈希见 `MANIFEST.csv` 与 `CHECKSUMS.sha256`。

---

# 四、说明

1. 本清单由构建脚本自动生成，**不包含清单自身**。
2. 若修改了包内任何文件，请重新运行生成脚本以更新清单。
3. 参赛队伍信息已填入 `01_开发设计文档/` 的封面表。
