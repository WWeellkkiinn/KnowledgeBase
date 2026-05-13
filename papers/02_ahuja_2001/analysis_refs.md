# 02_ahuja_2001

**关注重点**：研究方法  
**模型**：qwen3.6-27b  
**时间**：2026-04-27 10:43:03

---

### [1] Berk (1983) — An introduction to sample selection bias in sociological data
**在论文中的作用**：指出在因变量上进行抽样会导致严重的内部与外部效度威胁。
**与「研究方法」的联系**：为本文的样本构建策略提供核心方法论依据，解释为何研究必须纳入所有化工企业（无论是否产生突破性发明）的完整专利历史，从而彻底规避“因变量抽样偏差”，确保后续回归结果的无偏性与外部推广性。

---

### [2] Trajtenberg (1990b) — A penny for your quotes: patent citations and the value of information
**在论文中的作用**：论证专利引用次数是衡量技术创新技术重要性与经济价值的可靠代理指标。
**与「研究方法」的联系**：直接支撑因变量（突破性发明）的量化构建，为采用“同年度专利引用排名前1%”作为突破性发明识别阈值提供实证基础，并支持按专利申请年份进行队列比较的操作逻辑，确保技术重要性评估的时间一致性。

---

### [3] Hausman et al. (1984) — Econometric models for count data with an application to the patents–R&D relationship
**在论文中的作用**：系统提出适用于计数型数据的计量经济学建模框架。
**与「研究方法」的联系**：为本文选择泊松回归（Poisson regression）提供直接的方法论支撑，因研究因变量（企业年度突破性发明数量）为非负整数计数数据，该文献确立了基础模型设定的统计合理性，并指导了对数线性形式的构建。

---

### [4] Blundell et al. (1995) — Dynamic count data models of technological innovation
**在论文中的作用**：提出用于处理动态计数面板数据的样本前期泊松（Presample Panel Poisson）估计方法。
**与「研究方法」的联系**：直接指导本文如何控制企业层面的未观测异质性，通过将样本前期的突破性发明累计数量纳入模型，有效剥离不同企业在技术突破能力上的固有差异，提升纵向面板数据估计的准确性与因果推断力度。

---

### [5] Liang and Zeger (1986) — Longitudinal data analysis using generalized linear models
**在论文中的作用**：开发用于纵向数据分析的广义估计方程（GEE）方法。
**与「研究方法」的联系**：为本文处理纵向泊松面板数据中的序列相关性提供核心计量工具，支持采用GEE替代传统最大似然估计，从而在残差存在自相关或模型设定存在轻微误设时，获得更稳健的标准误与参数估计结果。

---

### [6] Stuart and Podolny (1996) — Local search and the evolution of technological capabilities
**在论文中的作用**：探讨技术密集型产业中知识基础的有效性与技术搜索的时间窗口特征。
**与「研究方法」的联系**：为自变量（新型技术、新兴技术）的测量提供操作化依据，直接支持设定“4-5年”作为知识折旧与技术熟悉度判断的时间阈值，确保变量构建符合技术演进的实际规律，并指导了稳健性检验中时间窗口的替代设定。
