# 01_bena_2017

**关注重点**：研究方法  
**模型**：qwen3.6-27b  
**时间**：2026-04-27 11:33:03

---

### [3] Acemoglu and Finkelstein (2008) — Input and Technology Choices in Regulated Industries: Evidence from the Health Care Sector
**在论文中的作用**：为处理组与对照组在政策冲击前可能存在不同趋势的问题提供计量处理范式。
**与「研究方法」的联系**：论文在基准双重差分模型中直接借鉴该文献的做法，通过引入处理组虚拟变量与政策冲击年份（1999年）的交互项，构建扩展的DID设定以吸收并控制两组间潜在的异质性时间趋势，从而强化因果识别的严谨性。

---

### [14] Bernard, Jensen, and Schott (2006) — Survival of the Best Fit: Low Wage Competition and the (Uneven) Growth of US Manufacturing Plants
**在论文中的作用**：提供衡量中国进口渗透率的标准变量构建方法。
**与「研究方法」的联系**：论文在排除“中国进口竞争”这一替代性解释时，直接沿用该文献的测算框架，在4位SIC行业层面构建滞后进口渗透率水平及其增长率变量，并将其与政策冲击交互纳入基准回归，以检验贸易渠道是否驱动了创新组合的变化。

---

### [18] Bloom, Draka, and Van Reenen (2015) — Trade Induced Technical Change? The Impact of Chinese Imports on Innovation, IT and Productivity
**在论文中的作用**：作为检验进口竞争渠道是否混淆主效应的关键对照文献。
**与「研究方法」的联系**：该文献指出中国进口竞争会正向促进企业创新，论文利用这一理论预测设计稳健性检验，将进口渗透率变量纳入DID模型进行控制。结果显示进口竞争交互项不显著且主效应依然稳健，从而在方法论上成功剥离了贸易冲击对技术创新方向的干扰。

---

### [25] Griliches (1990) — Patent Statistics as Economic Indicators: A Survey
**在论文中的作用**：奠定使用专利数据代理企业技术创新产出的理论基础。
**与「研究方法」的联系**：论文在变量构建阶段引用该文献，确立以美国专利商标局（USPTO）的专利授权数据作为衡量企业研发产出的核心指标，并在此基础上进一步通过文本解析技术将专利权利要求书细分为工艺创新与产品创新，为后续计量分析提供了可靠的微观数据基础。

---

### [29] Hall, Griliches, and Hausman (1986) — Patents and R&D: Is there a Lag?
**在论文中的作用**：为政策冲击与创新产出之间的时间滞后关系提供经验证据支持。
**与「研究方法」的联系**：论文在动态效应检验中发现政策冲击后的创新组合变化在次年（2000年）即显著显现且无显著滞后，直接引用该文献关于“研发支出与专利申请呈同期关系”的结论，从方法论上论证了无需设置长滞后窗口即可准确捕捉政策对技术创新方向的即时影响。

---

### [47] Schott (2008) — The Relative Sophistication of Chinese Exports
**在论文中的作用**：提供构建美国对华出口增长率变量的数据来源与测算依据。
**与「研究方法」的联系**：论文在排除“市场扩张/出口增长”渠道时，依据该文献提供的4位SIC制造业行业层面的美国对华出口数据，构建出口增长率变量并与政策冲击交互。该方法有效控制了因贸易壁垒降低带来的需求侧冲击，确保了DID模型仅捕捉劳动力成本渠道的净效应。

---

### [7] Ang, Cheng, and Wu (2014) — Does Enforcement of Intellectual Property Rights Matter in China? Evidence from Financing and Investment Choices in the High Tech Industry
**在论文中的作用**：提供中国省级层面知识产权保护力度的量化指标。
**与「研究方法」的联系**：论文在机制检验与替代解释排除中，直接采用该文献开发的IPR执法强度度量方法（基于原告胜诉率），构建随省份变化的知识产权保护变量。通过将其与处理组及政策冲击进行三重差分交互，从实证设计上排除了“因IP保护弱而转向保密而非专利”的替代性机制。

---

### [12] Autor, Levy, and Murnane (2003) — The Skill Content of Recent Technological Change: An Empirican Exploration
**在论文中的作用**：提供行业常规性任务（routine tasks）强度的分类标准与测算框架。
**与「研究方法」的联系**：论文在附录A的外部有效性检验中，引用该文献对职业任务常规性的分类体系，结合BLS数据构建行业层面的常规任务强度指标。通过回归分析验证工艺创新与该指标的负向关联，从方法论上交叉验证了本文专利文本分类指标的经济含义与测量效度。
