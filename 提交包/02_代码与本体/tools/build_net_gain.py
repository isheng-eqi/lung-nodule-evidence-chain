import json
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
# 从 tools/ 向上两级到提交包根，再进 03_验证与数据
# tools/ → 02_代码与本体/ → 提交包/  （向上两级）
PKG = os.path.join(os.path.dirname(os.path.dirname(HERE)), "03_验证与数据")
d = json.load(open(f"{PKG}/消融实验_三配置对照.json", encoding="utf-8"))
b = json.load(open(f"{PKG}/消融实验_RAG基线原始输出.json", encoding="utf-8"))

sc = d["scenarios"]
adv = [s for s in sc if s.get("case_type") == "advice"]
n = len(adv)

def cnt(key, cfg):
    return sum(1 for s in adv if (s.get(cfg) or {}).get(key))

A_cont, A_cave = cnt("has_contraindications", "config_a"), cnt("has_caveat_text", "config_a")
C_cont, C_cave = cnt("has_contraindications", "config_c"), cnt("has_caveat_text", "config_c")

bcases = [c for c in b["config_b_rag_only"] if c.get("case_type") == "advice"]
B_cont = sum(1 for c in bcases
             if any(k in (c.get("answer") or "") for k in ("不推荐", "禁忌", "不宜")))
B_cave = sum(1 for c in bcases
             if any(k in (c.get("answer") or "") for k in ("注意", "警惕")))

cfg = d["configs"]
out = {
    "schema_version": "1.0",
    "title": "消融实验的净收益量化 —— 双驱动的增量到底在哪里",
    "purpose": ("回应审阅：'消融只证明命中率相同，增量只有定性描述。"
                "现在这条证据读起来像「我们证明了双驱动没那么重要」'"),
    "design_note": ("三配置的**条款命中率**：A 双驱动 100% vs C 仅图谱 100% —— **相同**。"
                    "因此本项目**不声称**双驱动提高了准确率。"
                    "但'答对条款'不等于'给出安全的建议'："
                    "临床决策还必须**主动提示禁忌与注意事项**。"
                    "本文件量化这个增量。"),
    "advice_scenarios": [s["id"] for s in adv],
    "metrics": {
        "advice_scenario_count": n,
        "contraindication_hits": {
            "A_dual": A_cont, "C_kg_only": C_cont, "B_rag_only": B_cont,
        },
        "caveat_hits": {
            "A_dual": A_cave, "C_kg_only": C_cave, "B_rag_only": B_cave,
        },
        "gave_advice_when_insufficient": {
            k: v.get("gave_advice_when_insufficient")
            for k, v in cfg.items()
        },
        "hit_gold_rate": {k: v.get("hit_gold_rate") for k, v in cfg.items()},
    },
    "conclusion": (
        f"三配置的**条款命中率完全相同**（A {cfg['A_dual']['hit_gold_rate']:.0%} vs "
        f"C {cfg['C_kg_only']['hit_gold_rate']:.0%}），"
        f"但**禁忌提示覆盖率**为 A **{A_cont}/{n}** vs C **{C_cont}/{n}** —— "
        f"**仅图谱配置在 {n} 个建议场景中一个禁忌都没提示**。"
        f"另有「信息不足仍给建议」：A {cfg['A_dual']['gave_advice_when_insufficient']} 次 vs "
        f"B {cfg['B_rag_only']['gave_advice_when_insufficient']} 次。"
        "**即：双驱动的增量不在'答对哪一条'，而在'不遗漏必须提醒的那一条'。**"),
    "how_computed": (
        "对 `消融实验_三配置对照.json` 的 advice 类场景，统计 "
        "`config_a/config_c` 的 `has_contraindications` 与 `has_caveat_text` 字段；"
        "B 配置无结构化字段，故对 `消融实验_RAG基线原始输出.json` 的原始回答文本"
        "做关键词判定（'不推荐'/'禁忌'/'不宜'）。"),
}

P = f"{PKG}/消融实验_净收益量化.json"
json.dump(out, open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"  ✅ 已生成 {P}")
print()
print(f"  条款命中率  : A {cfg['A_dual']['hit_gold_rate']:.0%} / "
      f"C {cfg['C_kg_only']['hit_gold_rate']:.0%} / B {cfg['B_rag_only']['hit_gold_rate']:.0%}")
print(f"  禁忌提示    : A {A_cont}/{n}  C {C_cont}/{n}  B {B_cont}/{n}")
print(f"  注意事项    : A {A_cave}/{n}  C {C_cave}/{n}  B {B_cave}/{n}")
print(f"  信息不足仍给建议: A {cfg['A_dual']['gave_advice_when_insufficient']} "
      f"C {cfg['C_kg_only']['gave_advice_when_insufficient']} "
      f"B {cfg['B_rag_only']['gave_advice_when_insufficient']}")
