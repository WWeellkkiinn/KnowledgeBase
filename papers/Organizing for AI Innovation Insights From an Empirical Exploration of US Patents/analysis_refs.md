# Organizing for AI Innovation Insights From an Empirical Exploration of US Patents

**关注重点**：研究方法  
**模型**：qwen3.6-27b  
**时间**：2026-04-23 20:12:46

---

### 1. Giczy et al. (2022) — Identifying artificial intelligence (AI) invention: A novel AI patent dataset
**在论文中的作用**：为研究提供官方权威的AI专利识别标准与数据集，用于从海量专利中精准筛选出包含机器学习、自然语言处理、计算机视觉等八大核心技术的AI专利。
**与「研究方法」的联系**：直接决定了研究的数据基础与样本界定方法。论文摒弃了传统的关键词或IPC分类法，转而采用该文献提出的基于机器学习分类器（结合摘要、权利要求词嵌入及引文特征）的概率阈值识别法，显著提升了AI专利样本的精确度与召回率，是实证数据构建的核心方法依据。

### 2. Arts et al. (2018) — Text matching to measure patent similarity
**在论文中的作用**：提供专利文本相似度测度算法，用于在初步按年份和CPC代码匹配后，进一步筛选出与AI专利在技术主题上最接近的IT对照专利。
**与「研究方法」的联系**：是样本配对（Matching）方法的关键环节。通过引入该文本相似度测度，研究实现了AI与IT专利在技术范围与主题内容上的精细化对齐，有效控制了未观测的技术异质性，确保了后续比较分析的内部效度。

### 3. Iacus et al. (2012) — Causal inference without balance checking: Coarsened exact matching
**在论文中的作用**：提供粗粒度精确匹配（CEM）的计量经济学方法，用于在组别层面平衡AI与IT专利在权利要求数、前后向引文数及发明人数等可观测特征上的分布差异。
**与「研究方法」的联系**：直接支撑了研究的因果推断与选择偏差控制策略。论文采用该CEM程序生成样本权重，并在后续加权最小二乘（WLS）回归中应用，从而在计量模型层面严格排除了可观测协变量不平衡对核心结论的干扰，提升了实证结果的稳健性。

### 4. Dahlin & Behrens (2005) — When is an invention really radical? Defining and measuring technological radicalness
**在论文中的作用**：提供基于专利引文的知识重组独特性测度框架，用于量化专利的激进程度（创新幅度）。
**与「研究方法」的联系**：构成了核心因变量“激进程度”的操作化定义与计算公式。论文直接沿用该文献的Jaccard相似度指数与重叠得分（Overlap Score）算法，通过计算目标专利与过去三年已授权专利的引文重合度来反向衡量激进性，为创新幅度的量化提供了成熟且可比的计量基础。

### 5. Bena et al. (2022) — Shielding firm value: Employment protection and process innovation
**在论文中的作用**：提供基于专利权利要求文本的关键词识别方法，用于区分流程型（Process）与产品型（Product）专利主张。
**与「研究方法」的联系**：直接决定了核心因变量“流程导向程度”的测量方法。论文借鉴该文献的文本挖掘逻辑，通过检测权利要求前N个词中是否包含“process”或“method”等关键词来判定流程主张，并据此计算流程主张占比，实现了创新形式维度的客观量化。

### 6. Koenker (2005) — Quantile regression
**在论文中的作用**：提供分位数回归的计量模型框架，用于检验AI与IT专利在激进程度和流程导向上的差异是否在整个数据分布区间内成立，而非仅局限于均值。
**与「研究方法」的联系**：是研究稳健性检验与分布特征分析的核心统计工具。通过应用该分位数回归方法，论文突破了传统OLS仅关注条件均值的局限，验证了核心发现在不同分位点（0.1至0.9）上的一致性，增强了实证结论的普适性与方法严谨性。

### 7. Xue et al. (2012) — Efficiency or innovation: How do industry environments moderate the effects of firms’ IT asset portfolios?
**在论文中的作用**：提供行业环境特征（动态性、丰裕度、复杂性）的标准化测度指标，用于构建边界条件分析中的行业层面控制变量。
**与「研究方法」的联系**：直接支撑了边界条件（Boundary Conditions）的实证设计。论文采用该文献定义的基于四位数NAICS行业销售额波动率、增长率及赫芬达尔指数的计算方法，将宏观行业环境特征纳入调节效应检验框架，完善了多层面（企业-行业）实证模型的结构设定。

### 8. Arora et al. (2021) — Matching patents to Compustat firms, 1980-2015: Dynamic reassignment, name changes, and ownership structures
**在论文中的作用**：提供专利数据与企业财务/特征数据库（Compustat）的精准映射方案，用于获取申请人类型、企业规模、研发强度等边界条件变量。
**与「研究方法」的联系**：是跨数据库数据融合与微观企业层面变量构建的方法论基础。论文依赖该文献开发的DISCERN数据库匹配逻辑，解决了专利申请人名称变更、所有权结构复杂等数据清洗难题，确保了企业层面控制变量与专利观测值的准确对齐，保障了边界条件分析的可靠性。
