# 03_mikolov_2013

**关注重点**：研究方法  
**模型**：qwen3.6-27b  
**时间**：2026-04-26 09:36:59

---

### [1] Bengio et al. (2003) — A neural probabilistic language model
**在论文中的作用**：作为前馈神经网络语言模型（NNLM）的奠基性工作，被本文列为对比基线之一。
**与「研究方法」的联系**：本文提出的CBOW与Skip-gram架构正是针对该模型中非线性隐藏层导致的计算瓶颈进行简化，其方法设计直接源于对该架构复杂度公式的分析，并通过去除隐藏层与共享投影层实现了训练效率的跃升。

---

### [6] Dean et al. (2012) — Large Scale Distributed Deep Networks
**在论文中的作用**：介绍了DistBelief大规模分布式深度学习框架。
**与「研究方法」的联系**：本文的核心训练方法完全依赖该框架实现多副本并行训练与参数同步，使得在数十亿词规模语料上高效训练简化模型成为可能，是实验方法得以落地与扩展的关键计算基础设施。

---

### [7] Duchi et al. (2011) — Adaptive subgradient methods for online learning and stochastic optimization
**在论文中的作用**：提出了Adagrad自适应子梯度优化算法。
**与「研究方法」的联系**：本文在分布式训练过程中采用该算法作为自适应学习率策略，配合小批量异步梯度下降，构成了模型参数更新的核心优化方法，有效解决了大规模随机梯度下降中学习率衰减与收敛稳定性问题。

---

### [20] Mikolov et al. (2013) — Linguistic Regularities in Continuous Space Word Representations
**在论文中的作用**：定义了基于向量代数运算的词向量语义与句法关系评估范式。
**与「研究方法」的联系**：本文直接沿用并大幅扩展了该评估方法，构建了包含近两万道题目的综合测试集，通过向量加减运算与余弦相似度匹配来量化词向量质量，构成了本文验证模型有效性的核心评估方法论。

---

### [23] Mnih & Hinton (2009) — A Scalable Hierarchical Distributed Language Model
**在论文中的作用**：提出了可扩展的分层分布式语言模型及分层Softmax技术。
**与「研究方法」的联系**：本文的CBOW与Skip-gram架构直接采用基于哈夫曼树的分层Softmax替代传统全连接输出层，将输出计算复杂度从词表大小线性级降至对数级，是降低模型计算复杂度、实现高效训练的关键架构方法。

---

### [26] Rumelhart et al. (1986) — Learning internal representations by backpropagating errors
**在论文中的作用**：提出了反向传播算法。
**与「研究方法」的联系**：本文所有模型架构的参数训练均基于随机梯度下降与反向传播算法进行，是模型权重更新、误差反向传递与梯度计算的基础数学方法，贯穿了整个实验的训练流程。
