# 01_abood_2018

**关注重点**：研究方法  
**模型**：qwen3.6-27b  
**时间**：2026-04-26 08:40:54

---

### 1 Hochreiter et al. (1997) — Long short-term memory
**在论文中的作用**：提供了论文核心机器学习模型中处理专利文本摘要的长短期记忆网络（LSTM）架构基础。
**与「研究方法」的联系**：直接支撑了“宽深LSTM神经网络”剪枝方法的设计，用于捕捉专利文本中的序列依赖关系和语义特征，是自动化图谱构建中处理非结构化文本数据的核心算法依据。

---

### 2 Mikolov et al. (2013) — Efficient estimation of word representations in vector space
**在论文中的作用**：引入了word2vec词嵌入算法，用于将专利文本中的词汇转化为高维稠密向量。
**与「研究方法」的联系**：为机器学习模型提供了关键的文本特征表示方法，使模型能够自动处理同义词和语义相似性，大幅提升了基于文本的专利分类精度与泛化能力，是特征工程环节的核心技术。

---

### 3 Cheng et al. (2016) — Wide & deep learning for recommender systems
**在论文中的作用**：提出了Wide & Deep学习框架，启发了论文中结合稀疏元数据与深度文本特征的混合神经网络架构设计。
**与「研究方法」的联系**：直接指导了自动化剪枝模型的结构创新，将CPC代码和引用关系作为“宽”输入，LSTM文本特征作为“深”输入，实现了结构化元数据与非结构化文本特征的有效融合与联合训练。

---

### 4 Rosenblatt (1958) — The perceptron: a probabilistic model for information storage and organization
**在论文中的作用**：提出了感知机（Perceptron）算法，作为论文第三种机器学习剪枝策略的核心分类器。
**与「研究方法」的联系**：在结合随机特征投影（RFP）降维后，感知机算法被用于大规模专利数据的快速分类，验证了在高维稀疏特征空间下牺牲少量精度换取极高计算效率的方法可行性，丰富了自动化剪枝的算法选择。

---

### 5 Blum (2005) — Random projection, margins, kernels, and feature-selection
**在论文中的作用**：阐述了随机特征投影（RFP）技术，用于高维词袋模型特征空间的快速降维。
**与「研究方法」的联系**：直接支撑了第三种机器学习方法的特征工程环节，将数亿维的文本特征压缩至5000维，显著提升了感知机模型在千万级专利数据上的训练与推理效率，解决了大规模数据处理的维度灾难问题。

---

### 6 Dean et al. (2004) — MapReduce: simplified data processing on large clusters
**在论文中的作用**：提出了MapReduce分布式计算框架，用于支撑论文中大规模专利数据的处理流程。
**与「研究方法」的联系**：直接关联到研究方法的工程实现与可扩展性，论文依托该框架及Cloud Dataflow实现了种子扩展、特征提取、模型训练与全量分类的三大并行流水线，使自动化图谱构建能在1500万专利规模上高效运行。

---

### 7 Van Rijsbergen (1979) — Evaluation
**在论文中的作用**：奠定了信息检索领域评估指标的理论基础，论文据此采用F1分数作为核心评估标准。
**与「研究方法」的联系**：直接决定了研究方法的实验验证体系，通过计算少数类（种子专利）的F1分数并进行十折交叉验证，客观量化了不同机器学习剪枝策略在自动化图谱构建中的精度与召回平衡，确保了方法评估的科学性。

---

### 8 Deerwester et al. (1990) — Indexing by latent semantic analysis
**在论文中的作用**：提出了潜在语义分析（LSA）方法，论文将其应用于专利文本的奇异值分解（SVD）嵌入构建。
**与「研究方法」的联系**：直接支撑了第二种机器学习方法（浅层神经网络集成）中的文本特征提取流程，通过专利-词频矩阵的SVD压缩，将非结构化文本转化为低维稠密特征，提升了集成模型的分类鲁棒性。

---

### 9 Hinton et al. (2012) — Improving neural networks by preventing co-adaptation of feature detectors
**在论文中的作用**：提出了Dropout正则化技术，用于防止神经网络过拟合。
**与「研究方法」的联系**：直接应用于宽深LSTM模型的训练过程，通过在CPC/引用子网络和LSTM子网络中随机丢弃20%的输入节点，有效提升了模型在有限种子/反种子训练数据下的泛化能力与稳定性。

---

### 10 Ioffe et al. (2015) — Batch normalization: accelerating deep network training by reducing internal covariate shift
**在论文中的作用**：提出了批量归一化（Batch Normalization）技术，用于加速深度网络训练。
**与「研究方法」的联系**：直接集成于自动化剪枝神经网络的各隐藏层中，通过减少内部协变量偏移，显著加快了模型在专利数据上的收敛速度，是保障深度学习剪枝方法高效运行的关键训练技巧。

---

### 11 Clevert et al. (2015) — Fast and accurate deep network learning by exponential linear units (ELUs)
**在论文中的作用**：提出了指数线性单元（ELU）激活函数，用于替代传统的ReLU。
**与「研究方法」的联系**：直接应用于LSTM及全连接层的激活设计，实验表明ELU在保持模型精度的同时大幅减少了训练所需的迭代轮数，优化了自动化剪枝模型的训练效率与资源消耗。

---

### 12 De Lathauwer et al. (2000) — A multilinear singular value decomposition
**在论文中的作用**：提出了多元奇异值分解（Multilinear SVD）理论，为专利多模态数据的特征压缩提供数学基础。
**与「研究方法」的联系**：直接支撑了第二种机器学习方法中针对家族引用、文本、分类号和发明人引用等多类型专利数据的SVD嵌入构建，实现了高维稀疏特征向低维稠密空间的有效映射。

---

### 13 Baglama et al. (2005) — Augmented implicitly restarted lanczos bidiagonalization methods
**在论文中的作用**：提出了增广隐式重启Lanczos双对角化方法，用于大规模矩阵的SVD近似计算。
**与「研究方法」的联系**：直接解决了第二种机器学习方法中面临的计算瓶颈，由于专利特征矩阵规模达数百万行，该算法使得在有限算力下高效完成SVD降维成为可能，保障了自动化流程的工程可行性。

---

### 14 Skillicorn (2006) — Social network analysis via matrix decompositions
**在论文中的作用**：探讨了基于矩阵分解的社会网络分析方法，论文借鉴其思路处理专利引用网络。
**与「研究方法」的联系**：直接指导了第二种机器学习方法中家族引用特征的SVD嵌入构建，将专利间的引用关系转化为二进制矩阵并进行分解，使模型能够捕捉专利引用网络中的拓扑结构信息，丰富了元数据特征的表达维度。
