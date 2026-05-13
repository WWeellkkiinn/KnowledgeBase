# 02_arts_2018

**关注重点**：研究方法  
**模型**：qwen3.6-27b  
**时间**：2026-04-25 16:38:29

---

### [1] Jaffe et al. (1993) — Geographic Localization of Knowledge Spillovers as Evidenced by Patent Citations
**在论文中的作用**：奠定了利用专利分类（大类/子类）与申请日期构建案例对照样本（case-control matching）的经典研究范式，用于控制技术活动的先验地理集聚以识别知识溢出。
**与「研究方法」的联系**：作为本文方法对比的基准线，本文的文本匹配方法直接继承并改进了该文献的对照样本构建逻辑，将传统的USPC分类匹配替换为基于关键词Jaccard指数的文本匹配，从而在相同研究设计下检验新方法能否提供更精确的控制组。

---

### [2] Thompson (2006) — Patent citations and the geography of knowledge spillovers: evidence from inventor-and examiner-added citations
**在论文中的作用**：提出了一种基于专利内部变异（发明人添加引用 vs 审查员添加引用）的识别策略，有效规避了传统对照样本匹配不完美的问题。
**与「研究方法」的联系**：作为本文方法效度检验的“金标准”与复现目标。本文直接调用该文献的原始样本与地理局部化研究问题，通过对比文本匹配法与该文献内部变异法得出的实证结果，验证了新文本相似度度量在复杂因果识别场景中的外部有效性与稳健性。

---

### [3] Thompson and Fox-Kean (2005) — Patent citations and the geography of knowledge spillovers: a reassessment
**在论文中的作用**：系统批判了基于专利分类构建对照样本的方法，指出分类匹配存在严重的不完美性，可能导致知识溢出地理局部化估计产生偏误。
**与「研究方法」的联系**：为本文开发文本匹配方法提供了直接的方法论动机。本文通过专家盲评与全样本特征检验，量化证明了文本匹配能显著降低假阳性率（Type I errors），直接回应了该文献对传统分类匹配方法精度不足的质疑。

---

### [4] Li et al. (2014) — Disambiguation and co-authorship networks of the US patent inventor database 1975– 2010
**在论文中的作用**：提供了经过姓名消歧与地址清洗的美国专利发明人数据库，包含精确的经纬度与地理位置信息。
**与「研究方法」的联系**：构成本文地理局部化实证分析的核心数据基础设施。本文依赖该数据库准确映射发明人居住地，计算国别、州及核心基于统计区（CBSA）的地理重合率与空间距离（英里），这些指标是验证文本匹配对照样本是否有效控制先验技术集聚的关键因变量。

---

### [5] Hall, Jaffe, and Trajtenberg (2002) — The NBER patent citations data file: lessons, insights and methodological tools
**在论文中的作用**：建立了专利引文分析的技术领域分类体系与方法论工具集。
**与「研究方法」的联系**：为本文的专家验证环节提供抽样框架。本文依据该文献的技术类别划分，在不同技术领域内随机抽取基准专利，确保专家评分样本覆盖具有明确技术边界的领域，从而保障文本相似度度量外部效度检验的结构效度与可比性。

---

### [6] Chamberlain (1980) — Analysis of Covariance with Qualitative Data
**在论文中的作用**：提出了适用于定性数据的固定效应Logit模型估计方法。
**与「研究方法」的联系**：为本文知识溢出局部化回归分析（Table 9 Panel A）提供计量经济学基础。本文在复现Thompson (2006) 研究时采用该固定效应模型控制专利层面的不可观测异质性，确保在严格的方法论框架下对比文本匹配法与传统内部变异法的因果推断一致性。
