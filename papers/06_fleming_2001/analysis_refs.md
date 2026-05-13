# 06_fleming_2001

**关注重点**：研究方法  
**模型**：qwen3.6-27b  
**时间**：2026-04-27 11:25:09

---

### [1] Albert et al. (1991) — Direct validation of citation counts as indicators of industrially important patents
**在论文中的作用**：为将“后续专利引文数量”作为衡量发明有用性与技术重要性的核心因变量提供实证依据。
**与「研究方法」的联系**：直接支撑了论文因变量的构建逻辑与效度检验。作者引用该文献证明引文频次与技术价值高度相关，从而确立了使用专利引文数据作为技术搜索结果量化指标的方法论基础。

---

### [2] Argote et al. (1990) — The persistence and transfer of learning in industrial settings
**在论文中的作用**：为自变量构建中“知识遗忘/衰减率”参数的设定提供经验参考。
**与「研究方法」的联系**：直接指导了核心自变量（组件熟悉度与组合熟悉度）的数学构造。论文在计算历史使用频次时引入了指数衰减函数以模拟技术知识的时效性，并引用该文献中关于组织学习曲线衰减率的实证估计，作为将时间常数设定为五年的方法论依据。

---

### [3] Cameron and Trivedi (1986) — Econometric models based on count data: Comparisons and applications of some estimators and tests
**在论文中的作用**：为选择负二项回归模型及其具体参数化形式提供计量经济学理论支撑。
**与「研究方法」的联系**：直接决定了论文的核心统计建模策略。作者引用该文献论证了专利引文数据存在过度离散（方差大于均值）的特征，从而排除了泊松模型；同时依据该文献的推导，采用Negbin II参数化形式独立估计均值与离散度参数，并提供了验证该参数化适用性的回归检验方法。

---

### [4] Cameron and Windmeijer (1996) — R-squared measures for count data regression models with applications to health-care utilization
**在论文中的作用**：解释了为何在结果报告中不采用传统的R方指标来评估模型拟合优度。
**与「研究方法」的联系**：明确了计数数据最大似然估计的模型评估规范。论文引用该文献指出R方在负二项模型中存在方法论缺陷，且目前尚无公认的衡量离散度参数解释力的R方替代指标，从而确立了论文仅依赖对数似然值差异（Likelihood Ratio Test）进行模型比较与显著性检验的严谨做法。

---

### [5] Hausman et al. (1984) — Econometric models for count data with an application to the patents-R&D relationship
**在论文中的作用**：为负二项模型中误差项的概率分布设定提供数学推导依据。
**与「研究方法」的联系**：直接支撑了统计模型的底层概率结构构建。论文在推导负二项分布时，引用该文献建议将误差项服从伽马分布（Gamma distribution），并通过积分边缘化得到最终的负二项概率密度函数，确保了计数模型在数学上的可计算性与分布假设的合理性。

---

### [6] Long (1997) — Regression Models for Categorical and Limited Dependent Variables
**在论文中的作用**：作为计数数据回归与负二项模型推导的标准方法论参考手册。
**与「研究方法」的联系**：提供了论文整个计量框架的公式化表述与参数估计逻辑。作者直接引用该书完成从泊松模型到负二项模型的数学转换推导，明确了均值与方差的条件期望设定、最大似然估计的实现路径，以及离散度参数α的经济与统计解释方式。
