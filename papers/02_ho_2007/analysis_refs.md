# 02_ho_2007

**关注重点**：研究方法  
**模型**：qwen3.6-27b  
**时间**：2026-04-26 20:21:27

---

### [1] Rosenbaum et al. (1983) — The central role of the propensity score in observational studies for causal effects
**在论文中的作用**：奠定倾向得分匹配的理论基础，提出倾向得分作为“平衡得分”的核心概念。
**与「研究方法」的联系**：论文将倾向得分匹配作为预处理的核心技术之一，并在此基础上提出“倾向得分同义反复”原则，强调在实际操作中应以协变量平衡为最终检验标准，而非盲目依赖理论假设。

---

### [2] Rubin et al. (1992) — Characterizing the effect of matching using linear propensity score methods with normal distributions
**在论文中的作用**：提供匹配方法降低偏差与方差的理论证明。
**与「研究方法」的联系**：论文引用该文献证明在满足特定分布假设下，匹配能实现“等比例降偏”，为预处理步骤能同时降低估计偏差与方差（进而降低均方误差）提供理论支撑。

---

### [3] King et al. (2006) — The dangers of extreme counterfactuals
**在论文中的作用**：提出外推偏差问题及共同支撑域（凸包）检验方法。
**与「研究方法」的联系**：论文将其作为预处理阶段剔除需外推观测值的关键诊断工具，通过限制分析范围在共同支撑域内，直接切断参数模型因函数形式误设导致的模型依赖性。

---

### [4] Imai et al. (2006) — Misunderstandings among experimentalists and observationalists: Balance test fallacies in causal inference
**在论文中的作用**：批判传统假设检验在评估匹配平衡性中的谬误。
**与「研究方法」的联系**：论文直接采纳该观点，明确反对使用t检验或p值评估平衡性，转而推荐标准化均值差异、经验分位数图等描述性指标，重塑了预处理阶段的模型诊断流程。

---

### [5] Robins et al. (2001) — Comment on the Peter J. Bickel and Jaimyoung Kwon, ‘Inference for semiparametric models: Some questions and an answer’
**在论文中的作用**：阐述半参数模型推断中的双重稳健性（Double Robustness）性质。
**与「研究方法」的联系**：论文引用该理论证明“匹配预处理+参数估计”两步法具备双重稳健性，即只要匹配过程或后续参数模型中至少有一个设定正确，因果估计量仍保持一致性，极大提升了方法在实际应用中的可靠性。

---

### [6] Diamond et al. (2005) — Genetic matching for estimating causal effects: A new method of achieving balance in observational studies
**在论文中的作用**：提出基于遗传算法的自动化匹配优化方法。
**与「研究方法」的联系**：论文将其作为实现协变量平衡最大化的计算工具之一，纳入MatchIt软件包，使研究者能通过算法自动搜索最优匹配方案，避免主观选择带来的模型依赖。

---

### [7] Heckman et al. (1998) — Characterizing selection bias using experimental data
**在论文中的作用**：探讨匹配中偏差-方差权衡及协变量选择规则。
**与「研究方法」的联系**：论文引用该文献修正了“必须包含所有可用协变量”的教条，指出在控制组样本有限时，应遵循计量经济学传统规则权衡遗漏变量偏差与包含无关变量的效率损失，指导预处理阶段的变量筛选策略。
