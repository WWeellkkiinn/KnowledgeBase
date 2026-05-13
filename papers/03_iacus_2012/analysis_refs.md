# 03_iacus_2012

**关注重点**：研究方法  
**模型**：qwen3.6-27b  
**时间**：2026-04-25 17:13:56

---

### [1] Iacus et al. (2011) — Multivariate matching methods that are Monotonic Imbalance Bounding
**在论文中的作用**：奠定本文核心方法CEM的理论基础，首次提出单调不平衡界定（MIB）匹配方法类。
**与「研究方法」的联系**：直接定义了CEM所属的方法学类别，证明了CEM具备事前保证不平衡度不增加、各变量平衡边界相互独立的数学性质，是本文方法设计的理论基石。

---

### [2] Ho et al. (2007) — Matching as nonparametric preprocessing for reducing model dependence in parametric causal inference
**在论文中的作用**：论证匹配作为数据预处理步骤在降低参数模型依赖性方面的有效性。
**与「研究方法」的联系**：为本文强调“匹配旨在减少模型依赖而非替代建模”的方法论立场提供支撑，解释了为何CEM预处理后仍需结合回归等模型进行最终估计。

---

### [3] Imai et al. (2008) — Misunderstandings among experimentalists and observationalists about causal inference
**在论文中的作用**：提供因果推断中估计误差分解框架及区组划分（blocking）的方法学依据。
**与「研究方法」的联系**：本文借鉴其将匹配误差分解为“不平衡度”与“变量重要性”两部分的理论框架，并直接引用其关于随机实验中区组划分优于完全随机化的结论，用于拓展CEM在实验设计中的应用。

---

### [4] King et al. (2007) — When can history be our guide? The pitfalls of counterfactual inference
**在论文中的作用**：界定“模型依赖性”概念并警示反事实推断中的外推风险。
**与「研究方法」的联系**：本文方法学核心目标之一即为“界定模型依赖性”，直接沿用该文献对模型依赖性的定义，并以此论证CEM通过粗化粒度控制外推风险的方法学优势。

---

### [5] Dehejia et al. (1999) — Causal effects in nonexperimental studies: Re-evaluating the evaluation of training programs
**在论文中的作用**：提供评估匹配方法性能的标准基准数据集与倾向得分匹配对照方案。
**与「研究方法」的联系**：本文在模拟与实证部分直接采用该文献构建的数据生成过程与变量设定，作为检验CEM方法学性能（偏差、方差、不平衡度）的标准对照基准。

---

### [6] Diamond et al. (2005) — Genetic matching for estimating causal effects: A new method of achieving balance in observational studies
**在论文中的作用**：提供遗传匹配算法及复杂的非线性数据生成过程用于方法对比。
**与「研究方法」的联系**：本文在蒙特卡洛模拟中直接复用其设定的数据生成机制与评估指标，将CEM与遗传匹配进行方法学性能对比，凸显CEM在计算效率与误差控制上的优势。

---

### [7] Battistin et al. (2004) — The impact of measurement error on evaluation methods based on strong ignorability
**在论文中的作用**：分析测量误差对强可忽略性假设下评估方法的影响。
**与「研究方法」的联系**：本文方法学特性“对测量误差的近似不变性”直接针对该文献指出的传统匹配方法易受测量误差干扰的缺陷，通过粗化机制在方法设计上实现了对该问题的规避。
