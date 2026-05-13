# 02_thompson_2006

**关注重点**：研究方法  
**模型**：qwen3.6-27b  
**时间**：2026-04-26 19:53:52

---

### 1. Jaffe et al. (1993) — "Geographic knowledge spillovers as evidenced by patent citations."
**在论文中的作用**：奠定了利用专利引用数据追踪知识流动与地理局部性的基础分析框架。
**与「研究方法」的联系**：本文沿用了其“以专利引用作为知识溢出代理变量”的核心思路，但针对其案例对照匹配法（case-control matching）可能因技术分类选择偏差而高估局部效应的问题，提出了基于引用主体（发明人vs审查员）内部变异的新识别策略，实现了方法论上的迭代与修正。

---

### 2. Thompson and Fox Kean (2005) — “Patent citations and the geography of knowledge spillovers: a reassessment.”
**在论文中的作用**：系统批判了既往专利引用匹配方法的缺陷，指出按技术分类筛选对照专利会引入严重的匹配偏差。
**与「研究方法」的联系**：直接促使本文放弃传统的对照匹配设计，转而利用USPTO自2001年起标注的引用来源信息，构建“专利内固定效应”识别框架，从方法源头规避了样本选择偏差与伪局部性效应。

---

### 3. Jaffe et al. (2002) — “The meaning of patent citations: report on the NBER/Case Western Reserve survey of patentees.”
**在论文中的作用**：提供关于专利引用行为动机的微观调查证据。
**与「研究方法」的联系**：为本文识别策略的核心假设提供经验支撑，即发明人添加的引用更能真实反映技术知识的实际获取路径，而审查员引用多源于发明人遗漏。该文献使“将审查员引用作为无地理偏向对照组”的方法论设定具备实证合理性。

---

### 4. Chamberlain (1980) — “Analysis of covariance with qualitative data.”
**在论文中的作用**：提出条件Logit模型（conditional logit model）的理论基础。
**与「研究方法」的联系**：本文采用该模型处理被引专利固定效应，以解决组内观测值较少时传统无条件Logit面临的“附带参数问题”（incidental parameter problem），确保地理匹配几率比估计的一致性与无偏性，是本文计量识别的核心工具。

---

### 5. Katz (2001) — “Bias in conditional and unconditional fixed effects logit.”
**在论文中的作用**：系统比较条件与非条件固定效应Logit模型在有限样本下的偏差特性。
**与「研究方法」的联系**：在脚注9中被引用，用于从计量经济学原理层面论证为何必须采用条件Logit而非无条件Logit，强化了本文模型选择的方法严谨性，并解释了因组内无变异而损失部分样本的必然性。

---

### 6. Cockburn et al. (2003) — “Are all patent examiners equal? The impact of characteristics on patent statistics and litigation outcomes.”
**在论文中的作用**：探讨专利审查员专业背景与审查行为对专利统计结果的影响。
**与「研究方法」的联系**：在脚注10中被引用，作为本文稳健性检验的替代固定效应方案（使用审查员固定效应替代被引专利固定效应）。该文献支持了将审查员作为控制变量的可行性，验证了主模型对固定效应设定不敏感的方法稳健性。

---

### 7. Dun & Bradstreet (1998) — Who Owns Whom. North & South America.
**在论文中的作用**：提供企业所有权、子公司及关联企业目录数据。
**与「研究方法」的联系**：在结论部分被提及，作为未来优化自引剔除方法的数据工具。本文指出当前仅靠名称匹配剔除自引存在局限，该文献为后续研究如何更精确界定“企业内部引用”与“跨企业知识溢出”的方法边界提供了数据路径。
