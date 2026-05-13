# 03_ahuja_2001

**关注重点**：研究方法  
**模型**：qwen3.6-27b  
**时间**：2026-04-27 10:57:55

---

### [1] Berk (1983) — An introduction to sample selection bias in sociological data
**在论文中的作用**：论证研究采用全行业企业纵向面板数据而非仅筛选已证实为突破性专利的样本，以规避因“对因变量抽样”导致的内部与外部效度威胁。
**与「研究方法」的联系**：直接指导了样本选择策略的设计，确立了无偏样本构建原则，是实证研究设计阶段控制选择偏差的核心方法论依据。

---

### [2] Trajtenberg (1990b) — A penny for your quotes: patent citations and the value of information
**在论文中的作用**：提供以专利引用量衡量技术重要性的理论基础，并支持按专利申请年份进行同期群（cohort）比较及在模型中引入年份虚拟变量。
**与「研究方法」的联系**：决定了因变量（突破性发明）的操作化定义与计量模型中的时间控制策略，确保跨期专利数据在“被引用风险期”上的可比性。

---

### [3] Hausman et al. (1984) — Econometric models for count data with an application to the patents–R&D relationship
**在论文中的作用**：确立使用泊松回归（Poisson regression）处理非负整数计数型因变量的标准计量框架。
**与「研究方法」的联系**：直接决定了核心统计模型的选择，匹配了专利产出数据的离散分布特征，构成全文计量分析的基础架构。

---

### [4] Blundell et al. (1995) — Dynamic count data models of technological innovation
**在论文中的作用**：引入“样本前期面板泊松”（Presample Panel Poisson）方法，利用企业进入样本前的突破性发明数量控制未观测异质性。
**与「研究方法」的联系**：解决了纵向面板数据中企业固有创新能力的遗漏变量问题，通过前期表现代理不可观测特征，提升了因果推断的严谨性。

---

### [5] Liang and Zeger (1986) — Longitudinal data analysis using generalized linear models
**在论文中的作用**：提供广义估计方程（GEE）方法，用于处理纵向泊松数据中的序列相关与聚类效应。
**与「研究方法」的联系**：作为基准泊松模型的稳健性替代方案，直接优化了纵向数据的误差结构建模，通过纳入残差自相关机制增强计量结果的可靠性。

---

### [6] Stuart and Podolny (1996) — Local search and the evolution of technological capabilities
**在论文中的作用**：支持将4-5年设定为技术知识有效性与折旧的合理时间窗口，用于界定“新型技术”与“新兴技术”的测量滞后期。
**与「研究方法」的联系**：直接指导了自变量时间窗口的操作化设计，确保变量测量符合技术演进与知识衰减的客观规律，提升了指标构建的理论贴合度。

---

### [7] Greene (1997) — Econometric Analysis
**在论文中的作用**：提供多重共线性诊断标准（如标准误膨胀、系数符号敏感翻转等），用于检验模型设定的稳健性。
**与「研究方法」的联系**：直接应用于计量结果的质量控制环节，验证了核心自变量间高相关性未对回归估计造成干扰，保障了模型识别的有效性。
