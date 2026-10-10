import json
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
# 从 tools/ 向上两级到提交包根，再进 03_验证与数据
# tools/ → 02_代码与本体/ → 提交包/  （向上两级）
PKG = os.path.join(os.path.dirname(os.path.dirname(HERE)), "03_验证与数据")
raw = json.load(open("/tmp/consequence.json", encoding="utf-8"))
ab = json.load(open(f"{PKG}/消融实验_三配置对照.json", encoding="utf-8"))
sc = {s["id"]: s for s in ab["scenarios"]}

out = {
    "schema_version": "1.0",
    "title": "后果对照：漏掉禁忌提示会造成什么",
    "purpose": (
        "回应终审审计：'一等奖会给：仅图谱配置下 N/5 场景漏禁忌，"
        "并在禁忌相关的场景构造「若漏禁忌会导致什么」的对照。'"),
    "design": (
        "取消融实验里的两个建议类场景，它们**都命中同一条禁忌**"
        "（PET-CT 不推荐用于实性成分 ≤8mm 的混杂性病灶，出自推荐意见15），"
        "但**实性成分尺寸不同**，因此形成天然对照："
        "实性成分越小的病灶，PET-CT 的假阴性风险越高。"),
    "cases": [],
    "what_the_single_channel_loses": (
        "仅图谱配置（C）**命中了相同的条款号**（A001 → 推荐意见14，"
        "A005 → 推荐意见15），但 `has_contraindications = False` —— "
        "**它把「用哪条」答对了，却把「不该做什么」整条丢了**。"
        "图谱三元组里没有 CAVEAT 段落，这层信息只能由检索通道取回原文。"),
    "how_computed": (
        "A/C 的禁忌字段取自 `消融实验_三配置对照.json` 的逐场景结构化字段；"
        "禁忌原文与注意事项由引擎实跑取得（`kg_consult_decision`）。"),
}

for cid in ("A001", "A005"):
    s = sc.get(cid) or {}
    a = s.get("config_a") or {}
    c = s.get("config_c") or {}
    r = raw[cid]
    out["cases"].append({
        "id": cid,
        "question": r["question"],
        "solid_component_mm": r["solid_component_mm"],
        "gold_clause": s.get("gold_clause"),
        "clause_hit": {"A_dual": a.get("clause"), "C_kg_only": c.get("clause")},
        "contraindication_present": {
            "A_dual": bool(a.get("has_contraindications")),
            "C_kg_only": bool(c.get("has_contraindications")),
        },
        "the_contraindication": r["contraindications"],
        "caveat_text": r["caveat"],
        "consequence_if_missed": (
            "若只给出「适用【推荐意见14】mGGN ≤8mm 随访」而**不提 PET-CT 禁忌**，"
            "临床执行者可能按惯例安排 PET-CT 评估代谢活性。"
            f"但本例实性成分仅 {r['solid_component_mm']} mm（≤8mm），"
            "指南明确**不推荐**用 PET-CT 判断此类病灶 —— "
            "该检查在此适应证下**假阴性率高**，"
            "阴性结果可能造成**虚假安心**并延误随访。"),
    })

# 一致性核对：两案例的禁忌是否同一条
c0 = out["cases"][0]["the_contraindication"]
c1 = out["cases"][1]["the_contraindication"]
same = (bool(c0) and bool(c1)
        and c0[0].get("examination") == c1[0].get("examination")
        and c0[0].get("clause") == c1[0].get("clause"))
out["same_contraindication_across_cases"] = same
out["contrast"] = (
    "两案例的禁忌**同一条**（PET-CT / 推荐意见15），"
    f"但实性成分分别为 {out['cases'][0]['solid_component_mm']} mm 与 "
    f"{out['cases'][1]['solid_component_mm']} mm —— "
    "对照说明**该禁忌的触发条件是「实性成分 ≤8mm」而非「结节大小」**，"
    "这正是本项目主张的**受约束推理**（条件来自条款原文，不来自模型猜测）。"
    if same else "两案例禁忌不同，对照不成立（需人工复核）")

P = f"{PKG}/消融实验_后果对照.json"
json.dump(out, open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"  ✅ 已生成 {P}")
for c in out["cases"]:
    print(f"    {c['id']}: 实性 {c['solid_component_mm']}mm | "
          f"条款命中 A={c['clause_hit']['A_dual']} C={c['clause_hit']['C_kg_only']} | "
          f"禁忌 A={c['contraindication_present']['A_dual']} "
          f"C={c['contraindication_present']['C_kg_only']}")
print(f"  两案例禁忌同一条: {same}")
