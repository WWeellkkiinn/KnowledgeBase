# 05_fleming_2001

**关注重点**：研究方法  
**模型**：qwen3.6-27b  
**时间**：2026-04-27 11:15:25

---

### [1] Long (1997) — Regression Models for Categorical and Limited Dependent Variables
**在论文中的作用**：提供计数数据回归与负二项分布模型的理论基础，指导论文处理专利引用数据的过离散问题及参数估计流程。
**与「研究方法」的联系**：直接支撑核心统计方法的选择，论文依据该书推导负二项分布概率公式、设定误差项分布，并采用最大似然法进行均值与离散度参数的联合估计，确保模型符合计数数据的分布特征。

---

### [2] Cameron et al. (1986) — Econometric models based on count data: Comparisons and applications of some estimators and tests
**在论文中的作用**：论证负二项分布II型（Negbin II）参数化的适用性，指导方差与均值关系的建模策略。
**与「研究方法」的联系**：论文直接引用该文献的计量经济学框架，通过回归残差平方与预测值的关系验证Negbin II的稳健性，并据此设定条件方差函数，使自变量能够独立作用于引用均值与离散度参数，从而精准分离技术效用与不确定性。

---

### [3] King (1989) — Event count models for international relations: Generalizations and applications
**在论文中的作用**：提供事件计数模型中均值与方差效应独立估计的方法论依据。
**与「研究方法」的联系**：论文的核心计量创新在于将“技术不确定性”操作化为结果分布的方差，该方法直接借鉴King的模型扩展思路，允许在单一框架内分别估计自变量对一阶矩（均值）和二阶矩（离散度）的差异化影响，为检验探索与利用假说提供统计工具。

---

### [4] Hausman et al. (1984) — Econometric models for count data with an application to the patents-R&D relationship
**在论文中的作用**：提供负二项模型中误差项服从伽马分布的数学推导基础。
**与「研究方法」的联系**：论文在构建计数模型时，直接采用该文献提出的伽马分布密度函数对泊松均值进行积分，从而导出负二项分布的边际概率公式，为处理专利引用数据的异方差性与过离散问题提供严格的计量推导路径。

---

### [5] Argote et al. (1990) — The persistence and transfer of learning in industrial settings
**在论文中的作用**：为知识遗忘率（指数衰减参数）的设定提供经验依据。
**与「研究方法」的联系**：在构建“组件熟悉度”与“组合熟悉度”变量时，论文需设定知识随时间衰减的时间常数，直接参考该文献对组织学习曲线与知识折旧率的实证估计，从而科学量化历史专利使用频率的权重，完成核心自变量的操作化测量。

---

### [6] Albert et al. (1991) — Direct validation of citation counts as indicators of industrially important patents
**在论文中的作用**：验证专利引用次数作为技术重要性与价值代理变量的有效性。
**与「研究方法」的联系**：论文将后续引用量作为因变量，直接依赖该文献的实证结论来确立引用计数的信度与效度，确保因变量测量能够准确反映发明的实际效用，为后续均值与方差的双重建模奠定数据基础。

---

### [7] Trajtenberg et al. (1997) — University versus corporate patents: A window on the basicness of invention
**在论文中的作用**：说明专利细分类（subclass）体系的划分逻辑与历史一致性。
**与「研究方法」的联系**：论文将专利细分类作为技术组件的代理指标，引用该文献以证明专利分类系统能够跨时间稳定追踪技术构成，为独立变量的操作化测量提供可靠的数据来源与分类依据。

---

### [8] Cameron et al. (1996) — R-squared measures for count data regression models with applications to health-care utilization
**在论文中的作用**：指出计数数据回归中传统R方指标的不适用性，指导模型解释力评估。
**与「研究方法」的联系**：论文在报告结果时明确说明最大似然估计下R方测量的缺陷，并引用该文献讨论离散度参数解释力的评估难题，体现了对计量模型评估方法的严谨处理，避免了对模型拟合优度的误读。
