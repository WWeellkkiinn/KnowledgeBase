# 04_dahlin_2005

**关注重点**：研究方法  
**模型**：qwen3.6-27b  
**时间**：2026-04-26 08:33:25

---

### [1] Rosenkopf and Nerkar (2001) — Beyond local search: Boundary-spanning, exploration, and impact in the optical disk industry
**在论文中的作用**：为使用专利反向引用（backward citations）和跨类别引用来衡量技术新颖性与激进性提供理论基础。
**与「研究方法」的联系**：直接支撑了本文核心测量指标的设计逻辑。作者借鉴其“引用不同专利类别代表技术要素重组”的观点，将抽象的“新颖性”与“独特性”转化为可量化的引用结构差异，进而构建出基于重叠度评分（overlap score）的数学模型，使激进性测量从主观判断转向客观的数据驱动。

---

### [2] Ahuja and Lampert (2001) — Entrepreneurship in the large corporation: A longitudinal study of how established firms create breakthrough inventions
**在论文中的作用**：作为传统专利新颖性测量方法（零反向引用）的对照基准，用于方法对比与效度检验。
**与「研究方法」的联系**：在敏感性分析中被用于验证本文方法的优越性。实证结果显示，零引用标准无法识别出网球拍行业公认的技术突破，从而反证了仅依赖引用数量或有无引用的粗糙指标存在局限，凸显了本文提出的“引用结构相似度”方法在捕捉技术内容实质性断裂方面的方法学优势。

---

### [3] Stuart and Podolny (1996) — Local search and the evolution of technological capabilities
**在论文中的作用**：为计算专利间引用结构相似度提供方法论先例与计算框架。
**与「研究方法」的联系**：本文直接沿用并扩展了其基于引用重叠计算技术相似性的思路。作者将其发展为年度标准化重叠度评分（$os_{ti}/n_t$），通过控制每年专利总量并计算焦点专利与同年所有其他专利的相似度总和，解决了跨期比较的尺度不一致问题，构成了本文操作化定义的核心算法骨架。

---

### [4] Albert et al. (1991) — Direct validation of citation counts as indicators of industrially important patents
**在论文中的作用**：提供前向引用计数（forward citations）作为技术影响力的传统代理变量，用于交叉验证。
**与「研究方法」的联系**：在实证检验阶段，作者将本文方法识别出的专利与前向引用排名进行卡方检验与分布对比。该方法学对比不仅验证了新指标能捕捉到高影响力专利，更揭示了前向引用存在的时间累积偏差与社会地位混淆问题，从而在方法层面论证了重叠度模型在“事前识别”与“剥离非技术干扰”上的严谨性。

---

### [5] Dewar and Dutton (1986) — The adoption of radical and incremental innovations: An empirical analysis
**在论文中的作用**：代表依赖专家面板（expert panels）评估技术激进性的传统研究范式。
**与「研究方法」的联系**：被用于系统批判现有方法中的回顾性偏差（hindsight bias）与成功偏差（success bias）。这一批判直接推动了本文在方法设计上的转向：放弃依赖人类主观评分，转而采用连续归档的专利数据。该方法学选择确保了测量工具具备事前（ex ante）识别潜力，并有效规避了因仅关注市场成功技术而导致的样本选择偏差。

---

### [6] Fleming (2001) — Recombinant uncertainty in technological search
**在论文中的作用**：阐释技术新颖性来源于既有要素的重新组合，为引用模式映射技术内容提供理论桥梁。
**与「研究方法」的联系**：将“技术重组”这一抽象概念与专利引用网络的结构特征直接挂钩，使作者能够合理假设：引用结构的差异即代表底层技术知识的差异。这一理论支撑是本文能够将“新颖性、独特性、影响力”三大定性标准转化为可计算的定量阈值（如Condition A/B/C）的关键方法学前提。
