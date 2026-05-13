# 02_rosenkopf_2001

**关注重点**：研究方法  
**模型**：qwen3.6-27b  
**时间**：2026-04-27 10:50:08

---

### [1] Albert et al. (1991) — Direct validation of citation counts as indicators of industrially important patents
**在论文中的作用**：为使用专利引用频次作为衡量企业知识存量与技术影响力的核心指标提供实证依据。
**与「研究方法」的联系**：直接支撑了论文的数据来源选择与因变量构建逻辑，证明专利被引次数能够有效反映技术知识在后续演化中的保留与扩散程度，是量化“领域影响力”与“整体影响力”的方法论基石。

---

### [2] Henderson and Cockburn (1994) — Measuring competence? Exploring firm effects in pharmaceutical research
**在论文中的作用**：提供了以企业为分析单元、利用专利数据追踪技术能力与知识重组的成熟研究范式。
**与「研究方法」的联系**：指导了本文的样本筛选策略与纵向面板数据的构建方式，确立了以“企业-年份”为基本分析单元、通过专利引用网络刻画探索轨迹的操作化路径，并影响了控制变量（如专利数量）的设定。

---

### [3] Hausman, Hall, and Griliches (1984) — Econometric models for count data with an application to the patents–R&D relationship
**在论文中的作用**：为处理专利引用计数数据的统计建模提供计量经济学依据。
**与「研究方法」的联系**：直接决定了论文采用负二项回归（Negative Binomial Regression）作为核心分析模型，以解决因变量（专利被引次数）作为非负计数数据且存在过度离散（overdispersion）的统计特性，确保了回归估计的无偏性与稳健性。

---

### [4] Sorenson and Stuart (2000) — Aging, obsolescence and organizational innovation
**在论文中的作用**：为引入“引用文献平均年龄”作为控制变量提供理论依据。
**与「研究方法」的联系**：指导了模型中控制变量的设计，利用该文献关于技术老化与能力陷阱的发现，将引用文献年龄作为代理变量纳入回归，以排除因技术陈旧导致的引用衰减对探索行为与影响力关系的干扰，提升因果推断的严谨性。

---

### [5] Miyazaki (1995) — Building Competencies in the Firm: Lessons from Japanese and European Optoelectronic Firms
**在论文中的作用**：为光学磁盘技术专利子类的划分与界定提供外部验证标准。
**与「研究方法」的联系**：直接服务于数据清洗与样本框界定环节，作者通过对照该文献的专利分类体系，交叉验证并修正了光学磁盘技术对应的专利子类代码，确保了技术边界划分、探索类型分类及后续回归分析的数据准确性与可重复性。
