# Patent Citations and the Geography of Knowledge Spillovers: Evidence from nventor- and Examiner-Added Citations

Peter Thompson

Florida International University

March 2004

(This revision: June 2005)

I report new evidence for localized knowledge spillovers identified by within-patent variations in the geographic matching rates of citations added by inventors and citations added by examiners. Evaluated at the mean citation lag, inventor citations are 20 percent more likely than examiner citations to match the country of origin of their citing patent, while US inventor citations are 25 percent more likely to match the state or metropolitan area of their citing patent. The localization of intranational knowledge spillovers declines with the passage of time, but international borders present a persistent barrier to spillovers. (JEL O310, O340)

# I. Introduction

Well over a century has passed since Marshall’s (1890) observation that agglomeration of specialized industries is due in part to the localization of knowledge spillovers. The notion continues to resonate among economists [e.g. Jacobs (1969), Feldman (1994a, 1994b), Glaeser et al. (1992), Manski (2000)], and is implicit in most theories of economic growth [e.g. Romer (1990), Grossman and Helpman [(1991)]. Nonetheless, about the only direct evidence we have for localized knowledge spillovers is based on Jaffe, Trajtenberg and Henderson’s (1993 – hereafter JTH) pioneering analysis of patent citations using a case-control matching method.1

Thompson and Fox Kean (2005) recently argued that at least part of JTH’s evidence for strong localization effects is driven by imperfect matching that generates the appearance of localization effects even when none exist. Although they refine JTH’s matching method, they also contend that one cannot really trust evidence about localization effects obtained after selecting control patents by technology classification. This conclusion is particularly disheartening because patent citations remain the only counterexample to Krugman’s (1991:53) observation that “knowledge flows . . leave no paper trail by which they may be measured and tracked.”

This note reports results from an alternative identification scheme that continues to follow the paper trail left by patent citations. Since January 2001, the USPTO has indicated whether each citation in a patent was added by the inventor or by the examiner. The analysis exploits this new information to examine within-patent and within-examiner variations in the citing-cited geographic matching rates of citations added by inventors and those added by examiners.

Using a sample of over 27,000 citing-cited patent pairs, the estimations produce consistent evidence of localization effects at all geographic levels. Inventor citations are 20 percent more likely to match the country of origin of the citing patent than are examiner citations, while for domestic patents they are 25 percent more likely to match the citing patent’s location within the United States. The localization of intranational knowledge spillovers declines with the passage of time, but international borders present a persistent barrier to spillovers.

Section II of this note describes the data. Section III discusses the identification strategy. Section IV provides the results, and Section V briefly concludes.

# II. Data

The citing patents in the sample consist of all US patents granted during the first week of January 2003 and for which there is an institutional assignee. The analysis of citations is restricted to patents granted after January 1, 1976, the contents of which are available in machine-readable form. The numbers of every such patent referenced by at least one of the citing patents were collected. Programs in perl extracted the following details for each citing and cited patent: assignee name and location,2 inventor names and locations, date of issue, date of application, US classification codes, international classification codes, examiner’s field of search codes, and name of primary examiner. Additional coding noted whether a cited patent had an institutional assignee, and whether any citing-cited patent pair was a self-citation (i.e. the two patents had an assignee in common). Finally, the patent image files were then checked manually to detect which patents were added by the examiner, and to make numerous corrections.

The location assigned to each patent was determined by the residence of its first-named inventor.3 Patents report the town and state or country of residence of each inventor. Towns in the US were matched to counties, and, where relevant, to one of some 300 metropolitan statistical areas and to one of 17 consolidated metropolitan statistical areas (CMSAs) as defined by the US Census Bureau in 1990. This matching was initially done using correlation files provided by the Office of Social and Economic Data Analysis (OSEDA) of the University of Missouri. Some 1,000 place names not in the OSEDA files, usually neighborhoods in major metropolitan areas, were identified using digital maps available from http://maps.yahoo.com.

To check that the technology coverage of the sample is not unusual, the threedigit primary classes of the citing patents in the sample were compared with the universe of patents granted between 1997 and 1999, taken from the NBER patent data file. The distribution of the sample across technology classes is highly correlated with the corresponding distribution in the NBER data file, but there are five outliers.4 No doubt, part of this difference is attributable to changes in the patent population during the five years or so that separate the samples. Nonetheless, the results to be presented in Section IV were checked after eliminating these five technology classes. Doing so did not change the results reported.

Table 1 provides some basic information about the sample. After the elimination of seven cited patents5 , the sample contains 31,377 citations generated by 2,670 citing patents, an average of just under twelve citations made by each patent. Examiners are a very important source of citations, accounting for over 41 percent of the sample. Moreover, they accounted for all the citations made by 38 percent of the citing patents, compared with only 8.5 percent for inventors. Surprisingly, the selfcitation rate is only a little higher among inventor citations (12.5 percent against 10.9 percent), which suggests at the least a certain casualness with which inventors prepare their applications.

TABLE 1. Summary Statistics 

<table><tr><td colspan="4">CITING PATENTS</td></tr><tr><td>NUMBER OF OBSERVATIONS</td><td></td><td></td><td>2,670</td></tr><tr><td>CITATIONS PER PATENT</td><td></td><td></td><td>11.8</td></tr><tr><td>FRACTION OF CITING PATENTS WITH ALL CITATIONS ADDED BY EXAMINER</td><td></td><td></td><td>.380</td></tr><tr><td>FRACTION OF CITING PATENTS WITH ALL CITATIONS ADDED BY INVENTOR</td><td></td><td></td><td>.085</td></tr><tr><td colspan="4">CITED PATENTS, ISSUED AFTER JAN 1, 1976.</td></tr><tr><td></td><td>ALL CITATIONS</td><td>ADDED BY INVENTOR</td><td>ADDED BY EXAMINER</td></tr><tr><td>NUMBER OF OBSERVATIONS</td><td>31,377</td><td>18,413</td><td>12,964</td></tr><tr><td>MEAN FILING DATE</td><td>May, 1992</td><td>May, 1991</td><td>May, 1993</td></tr><tr><td>MEDIAN FILING DATE</td><td>Apr, 1994</td><td>Feb, 1993</td><td>Nov, 1995</td></tr><tr><td>MEAN ISSUE DATE</td><td>Jun, 1994</td><td>May, 1993</td><td>Nov, 1995</td></tr><tr><td>MEDIAN ISSUE DATE</td><td>Mar, 1996</td><td>Dec, 1994</td><td>Mar, 1998</td></tr><tr><td>FRACTION SELF-CITATIONS</td><td>.118</td><td>.125</td><td>.109</td></tr><tr><td>FRACTION INSTITUTIONAL ASSIGNEE</td><td>.906</td><td>.904</td><td>.910</td></tr></table>

# III. Identification Strategy

The identification strategy rests on two assumptions. The first is that examiners, who work in a single campus located in Alexandria, VA and most commonly enter the USPTO directly from college, cannot be learning about prior art because of geographic proximity to related technological activities.6 The second is that an inventor citation is more likely to represent a true knowledge flow than is an examiner citation. The clearest support for the second assumption comes from the NBER/Case Western Reserve survey of patentees [Jaffe, Trajtenberg, and Fogarty (2002)], from which it was found that examiner citations are more likely to reflect ignorance on the part of the inventor.

It is not necessary that all knowledge flows be captured by inventor citations. The NBER/Case Western Reserve survey documents several sources of noise in the citations data. Inventors may cite prior art by conducting a search (or having their lawyers do so) after completing the invention, thereby adding citations that do not reflect a knowledge flow.7 Inventors may also fail to cite prior art that they do know about, and these are eventually added by the examiner. These sources of noise reduce the power of tests of geographic differences between inventor and examiner citations, and lead to a systematic underestimate of the magnitude of differences in geographic matching rates. However, the tests in this paper, as in previous work, turn on the statistical significance of any differences found. Power lost by noise can always be recovered by increasing sample size.

But this identification scheme will fail, and produce spurious evidence that knowledge flows are constrained by geography, if those examiner citations that do represent knowledge flows are less likely to produce geographic matches than inventor citations. One mechanism generating this bias is as follows8 Suppose that all citations capture a knowledge flow with equal probability. Knowledge flows by word of mouth, so that knowledge from more distant sources has passed through more agents before reaching an inventor. Because of the longer chain, the inventor does not learn of the source of ideas with more distant sources. If the inventor also does not undertake a patent search of these ideas, he or she is more likely to cite local patents, while the examiner fills in the gap.

This alternative story appears observationally equivalent to the identification scheme, so it is difficult to discount directly. However, if the story is correct, one would expect that examiners, who are citing sources that have passed through a longer chain, will on average cite older patents. The data show the opposite. Figure 1 plots the distribution of cited patent ages by citation source. Not only is the mean age of examiner citations lower, it is readily verified that the age of examiner citations first-order stochastically dominates the age of inventor citations. Even if we remove from the sample cited patents younger than five years old (because examiners are particularly likely to cite them), stochastic dominance holds.

![](images/cba60d0d7f4c21c89f94251822aea58f8b832310a2a845dffb3f884390b9032b.jpg)

<details>
<summary>bar</summary>

| Age of cited patent | Examiner citations | Inventor citations |
| :--- | :--- | :--- |
| 0-1 | 0.002 | 0.000 |
| 1-2 | 0.003 | 0.000 |
| 2-3 | 0.014 | 0.003 |
| 3-4 | 0.035 | 0.012 |
| 4-5 | 0.049 | 0.027 |
| 5-6 | 0.056 | 0.049 |
| 6-7 | 0.045 | 0.055 |
| 7-8 | 0.035 | 0.061 |
| 8-9 | 0.027 | 0.050 |
| 9-10 | 0.021 | 0.040 |
| 10-11 | 0.017 | 0.036 |
| 11-12 | 0.014 | 0.032 |
| 12-13 | 0.012 | 0.028 |
| 13-14 | 0.011 | 0.026 |
| 14-15 | 0.010 | 0.023 |
| 15-16 | 0.009 | 0.020 |
| 16-17 | 0.007 | 0.016 |
| 17-18 | 0.006 | 0.017 |
| 18-19 | 0.005 | 0.013 |
| 19-20 | 0.005 | 0.011 |
| 20-21 | 0.005 | 0.011 |
| 21-22 | 0.004 | 0.010 |
| 22-23 | 0.004 | 0.009 |
| 23-24 | 0.004 | 0.010 |
| 24-25 | 0.004 | 0.008 |
| 25-26 | 0.004 | 0.007 |
| 26-27 | 0.004 | 0.008 |
| 27-28 | 0.003 | 0.007 |
| 28-29 | 0.003 | 0.005 |
| 29-30 | 0.002 | 0.003 |
| 30+ | < 0.01 | < 0.01 |
</details>

FIGURE 1. Age distribution of cited patents, by citation source.

# IV. Results

All results in this section were obtained after eliminating self-citations from the sample. International localization effects are assessed by comparing the country of residence of the first-named inventor in the citing and cited patents. The variable MATCH COUNTRY was set to one if both inventors resided in the same country, and zero otherwise. Intranational localization effects are reported at three levels. First, if the citing patent has a US origin, does the cited patent have the same state origin as the originating patent (MATCH STATE)? Second, if the origin of the citing patent is in one of the 300 or so MSAs, does the cited patent share the same MSA (MATCH MSA)? Third, if the origin of the citing patent is in one of the 17 CMSAs, does the cited patent share the same CMSA (MATCH CMSA)? The first column of Table 2 indicates the number of observations available at each level of analysis. After eliminating self-citations, 27,665 observations are in the sample. Of these, 18,737 citing patents have a US origin, 17,826 have an origin in an MSA, and 9,721 have an origin in a CMSA.

TABLE 2. Crude Geographic Matching Rates 

<table><tr><td rowspan="2"></td><td rowspan="2">N</td><td rowspan="2">ALL OBSERVATIONS</td><td colspan="2">CITATIONS ADDED BY ..</td></tr><tr><td>INVENTOR</td><td>EXAMINER</td></tr><tr><td>MATCH COUNTRY</td><td>27,665</td><td>.539</td><td>.584</td><td>.476</td></tr><tr><td>MATCH  $STATE^a$ </td><td>18,737</td><td>.111</td><td>.115</td><td>.101</td></tr><tr><td>MATCH  $CMSA^b$ </td><td>9,721</td><td>.104</td><td>.111</td><td>.090</td></tr><tr><td>MATCH  $MSA^c$ </td><td>17,826</td><td>.093</td><td>.098</td><td>.082</td></tr></table>

Self-citations excluded. a Conditional on the citing patent having a US inventor. b Conditional on the citing patent coming from a CMSA. c Conditional on the citing patent coming from an MSA.

The remaining columns of Table 2 summarize the crude geographic matching rates. The table presents a uniform picture at all geographic levels, with matching rates for inventor citations exceeding the rates for examiner citations by between 7 and 23 percent. Of course, the localization effects suggested by these crude matching rates may be confounded with important composition effects, whereby examiner citations just happen to figure more prominently in patents that exhibit lower geographic matching rates. To eliminate such potential confounding, I turn now to conditional logit estimation.

Panel A of Table 3 reports odds ratio estimates from logits with fixed effects for each cited patent. Two general comments are in order. First, because the number of observations per citing patent is modest, the bias induced by the well-known incidental parameter problem may be quantitatively important.9 Estimation is therefore carried out using Chamberlain’s (1980) conditional logit model. Doing so means, first, that we cannot obtain consistent estimates of the patent fixed effects, numbers that might be of considerable interest in their own right. Second, when the outcome is identical for all observations within a group (either no citations in a single patent have a match, or they all do), the fixed effect alone is a sufficient statistic for the estimated matching rate. Such observations do not contribute useful information in estimating the parameters of interest. Table 3 consequently reports sample sizes reflecting the number of observations that make a positive contribution to the likelihood. 10

Each model contains three regressors. First, a dichotomous variable is set equal to one if the citation was added by the inventor, zero otherwise. An odds ratio in excess of one provides prima facie evidence of localization effects. Second, a dichotomous variable is set equal to one if the cited patent has no institutional assignee. Because the geographic distribution of non-institutional patents differs markedly from institutional patents (they are more likely to be American, and more likely to be from outside metropolitan areas), it was expected that the type of assignee would influence the matching rate. Third, many theories of technological diffusion

tional logit estimator when T varies by group to this extent. My colleague, Jonathan Hill, kindly ran some simulations on samples with the degree of variation in group size exhibited by the sample, and found that bias appears to be a significant problem in the unconditional logit.

10 A significant number of observations are lost, especially in the finer geographic classes, because of the lack of within-group variation in the dependent variables. One way to reduce the loss of effective observations is to estimate a model with fewer fixed effects, which reduces the number of groups with no variation in the dependent variable. One candidate for an alternative set of fixed effects is the primary examiner on the citing patents, who have distinct specialties [Cockburn, Kortum and McHale (2003)] and therefore may serve as an adequate, albeit somewhat cruder, control. With 975 primary examiners in the sample, the mean number of observations per examiner is about three times the mean number of observations per citing patent. The results are not modified by this alternative set of controls, and so are not reported here

suggest that matching rates may be lower the older the cited patent, so a linear trend for the age of the cited patent is included.11

TABLE 3. Odds Ratios for Geographic Matching Rates 

<table><tr><td>DEPENDENT VARIABLE</td><td> $N^a$ </td><td>INVENTOR CITATION</td><td>NON- INSTITUTIONAL</td><td>CITED PATENT AGE</td><td>AGE X INVENTOR CITATION</td></tr><tr><td colspan="6">PANEL A</td></tr><tr><td>MATCH COUNTRY</td><td>22,198</td><td>1.207(3.76)</td><td>1.28(4.32)</td><td>0.990(-3.33)</td><td>——</td></tr><tr><td>MATCH STATE</td><td>11,864</td><td>1.31(3.17)</td><td>1.072(0.78)</td><td>0.966(-6.51)</td><td>——</td></tr><tr><td>MATCH CMSA</td><td>6,036</td><td>1.292(2.10)</td><td>0.832(-1.37)</td><td>0.966(-4.35)</td><td>——</td></tr><tr><td>MATCH MSA</td><td>10,470</td><td>1.300(2.76)</td><td>0.805(-2.07)</td><td>0.954(-7.64)</td><td>——</td></tr><tr><td colspan="6">PANEL B</td></tr><tr><td>MATCH COUNTRY</td><td>22,198</td><td>1.151(1.73)</td><td>1.281(4.33)</td><td>0.988(-2.66)</td><td>1.00(0.76)</td></tr><tr><td>MATCH STATE</td><td>11,864</td><td>1.782(4.07)</td><td>1.072(0.78)</td><td>0.988(-1.25)</td><td>0.969(-2.74)</td></tr><tr><td>MATCH CMSA</td><td>6,036</td><td>1.666(2.50)</td><td>0.831(-1.38)</td><td>0.987(-0.87)</td><td>0.972(-1.57)</td></tr><tr><td>MATCH MSA</td><td>10,470</td><td>1.732(3.40)</td><td>0.804(-2.09)</td><td>0.976(-2.09)</td><td>0.970(-2.22)</td></tr></table>

Z-scores in parentheses. a Number of observations contributing to the likelihood function.

The estimated odds ratios for INVENTOR CITATION are in general a little higher than the crude geographic matching rates reported in Table 2. Inventor citations are 20 percent more likely to show a country match than are examiner citations, which is similar to the crude rates; but they are 30 percent more likely to show a state, CMSA or MSA match, which are about 1.5 times the corresponding crude matching rates.

The two additional controls behave in just the way anticipated. First, the matching rate for non-institutional patents is higher at the country level, because the majority of the sample consists of domestic patents and most non-institutional patents are domestic. In contrast, the matching rate is lower at the MSA and CMSA levels, because non-institutional patents are less likely to be found in metropolitan areas. The intermediate level of the state shows no difference. Second, there is consistent evidence at all geographic levels that matching rates decline with the age of the cited patent. Quantitatively, the effect is quite marked. The odds ratio falls by between 1 and 5 percent per year, so that, say, a ten year old cited patent is between 10 and 50 percent less likely to generate a match than the most recent cited patent.12 However, the estimated rate of decline is markedly lower for the country matching rate.

The decline in matching rates for older cited patents does not constitute direct evidence that knowledge spillovers become less localized with the passage of time. In principle, it is possible to distinguish between two confounding effects – the diffusion of industrial activity over wider geographic areas and changes in the localization of spillovers – by adding to the regressions an interaction term between the indicator variable for inventor citations and the cited patent age. Panel B of Table 3 reports the results. The odds ratios for inventor citations, which have risen markedly at the intranational levels, now measure the effect for the youngest cited patents. The results continue to show that increases in the age of the cited patent reduce matching rates, reflecting diffusion of technological activity both intranationally and nationally.

The odds ratios for the interaction term tell an interesting story. It is essentially unity at the international level, while all estimates of the odds ratio at intranational levels are less than one. Put another way, knowledge spillovers appear to become less localized over time within the US, but not between countries. However, at the sample mean age, 11.4 years, all four levels of analysis show very similar degrees of localization; the estimated odds ratios at this age are 1.21 (country), 1.25 (state), 1.23 (CMSA), and 1.25 (MSA), each of which is significantly greater than unity at the customary five percent level. To aid interpretation of these results, Figure 2 plots the odds ratio for inventor citations by age of the cited patent for country and MSA matching.13 There is a modest, but persistent, localization of knowledge spillovers at the international level. At the MSA level, there are strong localization effects for the most recent cited patents, but this effect decays with time so that, by age 14, the effect is no longer statistically significant.

This decay of localization effects within the US. but not across countries is just what one would expect if the decay of localization is caused primarily by inventor relocation, which is much more likely to occur between regions of the US than between countries. While 5.6 percent of the 2001 US population had changed their county of residence during the prior year and 2.8 percent had changed state, only 0.6 percent had arrived from abroad [US Census (2004)].

Table 4 reports some further analyses. In Panel A, a distinction is made between patent pairs for which the citation crosses technology classes, and those pairs for which both patents share the same primary three-digit class. One might expect the more homogeneous a network, the more readily it transcends geography.14 One would therefore expect geography to matter more when technology classes differ. This is exactly what the data show. Intranationally, geographic matches are more likely when patent pairs have the same primary technology class (surprisingly the same does not appear to be true at the country level). After controlling for technology class level effects, localization effects turn out to be markedly stronger at every level when patent pairs do not share the same technology class.

Almeida and Kogut (1999), among others, have shown that localization effects are stronger in certain high-technology regions, such as Silicon Valley, the Route 126 corridor and Austin, TX, than in other regions. The evidence is consistent with the widespread perception that in these regions ideas are stimulated by local technologi-

PANEL A. Odds Ratio for Country Match   
![](images/b95060fab58108b0360f1e0b0116c063ac135f60000cbd926b5b236bde9d9530.jpg)

<details>
<summary>line</summary>

| Age of cited patent (years since filing) | Odd ratio |
| ---------------------------------------- | --------- |
| 0                                        | 1.1       |
| 5                                        | 1.15      |
| 10                                       | 1.2       |
| 15                                       | 1.25      |
| 20                                       | 1.3       |
| 25                                       | 1.35      |
| 30                                       | 1.4       |
</details>

PANEL B. Odds Ratio for MSA Match

![](images/de36ed887cd903ba3f12d52e6a39275063b173761c0eeff74949c165ee802ff8.jpg)

<details>
<summary>line</summary>

| Age of cited patent | Odd ratio |
| ------------------- | --------- |
| 0                   | 1.7       |
| 5                   | 1.5       |
| 10                  | 1.3       |
| 15                  | 1.1       |
| 20                  | 0.9       |
| 25                  | 0.8       |
| 30                  | 0.7       |
</details>

FIGURE 2. Odds ratios for inventor added citations, by age of cited patent.

TABLE 4. Odds Ratios for Geographic Matching Rates   
Conditioning on Technology Classification Match or Assignee Location 

<table><tr><td rowspan="3"></td><td colspan="3">A. TECHNOLOGY CLASSIFICATION MATCH</td><td colspan="2">B. ASSIGNEE LOCATION</td></tr><tr><td colspan="2">INVENTOR CITATION</td><td rowspan="2">TECHNOLOGYMATCH</td><td colspan="2">INVENTOR CITATION</td></tr><tr><td>MATCH</td><td>NO MATCH</td><td>ASSIGNEE NOT INCA, TX, MA</td><td>ASSIGNEE IN CA,TX, OR MA</td></tr><tr><td>MATCH COUNTRY</td><td>1.137(2.04)</td><td>1.273(3.91)</td><td>1.047(0.77)</td><td>1.189(2.95)</td><td>1.236(2.19)</td></tr><tr><td>MATCH STATE</td><td>1.216(1.85)</td><td>1.427(3.26)</td><td>1.147(1.24)</td><td>1.220(1.74)</td><td>1.450(2.87)</td></tr><tr><td>MATCH CMSA</td><td>1.232(1.44)</td><td>1.447(2.28)</td><td>1.317(1.76)</td><td>1.285(1.49)</td><td>1.337(1.63)</td></tr><tr><td>MATCH MSA</td><td>1.162(1.29)</td><td>1.499(3.24)</td><td>1.269(1.87)</td><td>1.163(1.25)</td><td>1.600(2.99)</td></tr></table>

Z-scores in parentheses. Odds ratios for NON-INSTITUTIONAL and CITED PATENT AGE are similar to previous results and hence are not reported here.

cal developments to a greater extent than elsewhere. Panel B of Table 4 reports separate regressions after excluding California, Texas and Massachusetts, and for these states alone.15 Consistent with prior evidence, localization effects are stronger in these states, but geography does matter elsewhere.

# V. Conclusions

This paper combines Jaffe, Trajtenberg and Henderson’s (1993) innovative use of patent citations to study knowledge flows with a new identification strategy based on differences between geographic matching rates for inventor-added and examineradded citations. The paper has produced prima facie evidence that knowledge spillovers are geographically localized both internationally and intranationally. It was also found that only intranational localization effects become weaker with the passage of time. These are not surprising results. In particular, the finding that intranational but not international localization effects decay with time is consistent with the conventional wisdom that geography matters because tacit knowledge is embodied in individual researchers, who relocate frequently within in the United States but only infrequently across international borders.

Of course, these results should be interpreted with caution Two issues merit particular attention. First, the elimination of self-citations – in this and in all prior work – remains far from satisfactory, in ways that may well generate false localization effects. Although I have manually checked the sample for cases where company names are sufficiently similar to identify self-citations between parents and their subsidiaries, partners, and joint ventures, this effort can only get us so far. One could presumably advance the process using directories of company ownership [e.g. Dun & Bradstreet (1998)]. But, daunting as that task would be, one must then decide when a citation is a self-citation and when it is a spillover. Presumably, the judgment depends on the degree of interaction taking place between related firms. This does not seem to be a criterion that lends itself to measurement.

Second, the analysis fails to distinguish adequately between the effects of geography on knowledge spillovers and the effects of industry boundaries. For example, patent examiners may be more likely than inventors to cite related technologies in different industries, and in so doing we confound the effects of industry with the effects of geography. A first look at the data raises the hope that this is not too great a concern, because for various technological criteria it turns out that examiners are less likely to cite across technology classes. Inventor citations match the US primary class 41 percent of the time, compared with 54 percent for examiner citations. Examiner citations also match the US sub-class, the international classification code, and the field of search more often. However, these numbers are only suggestive. Because of the way that examiners undertake searches for prior art, it is possible that they are more likely to cite prior art within the same technology class, while at the same time unobserved heterogeneity within classes implies that they are less likely to cite prior art in the same industry. It is not obvious to me how one might answer this question from information contained in patent data, but it should encourage caution: we cannot be sure whether geography or industry boundaries present the real barrier to knowledge spillovers.

Dealing with these, and possibly other, caveats, will no doubt require more work on both data collection and experimental design. But, before undertaking that considerable effort, there is perhaps a more immediate task: to figure out exactly what it means from the perspective of policy design and welfare to have, say, a 20 percent greater matching rate for inventor citations. The most appropriate line of inquiry here looks to be introducing such differences in spillover rates to an appropriate calibrated growth model. This seems to me to be the next task at hand.

# References

Agrawal, Ajay, Iain M. Cockburn, and John McHale (2003): “Gone but not forgotten: labor flows, knowledge spillovers, and enduring social capital.” NBER working paper 9950.   
Agrawal, Ajay., Devesh Kapur, and John McHale (2004): “Defying distance: examining the influence of the diaspora on scientific knowledge flows.” University of Toronto: Working paper.   
Almeida, Paul. (1996): “Knowledge sourcing by foreign multinationals: patent citation analysis in the US semiconductor industry.” Strategic Management Journal, 17(Winter Special Issue):101-23.   
Audretsch, David B., and Maryann P. Feldman (2003): “Knowledge spillovers and the geography of innovation.” In V. Henderson and J.F. Thisse, eds, Handbook of Urban and Regional Economics, volume 4, forthcoming.   
Breschi, Stefano, and Francesco Lissoni (2004): “Knowledge networks from patent data: methodological issues and research targets.” CESPRI, Milan: Working paper no. 150.   
Chamberlain, Gary (1980): “Analysis of covariance with qualitative data.” Review of Economic Studies, 47:225-238.   
Cockburn, Iain M., Samuel Kortum, and Scott Stern (2003): “Are all patent examiners equal? The impact of characteristics on patent statistics and litigation outcomes.” NBER working paper 8980.   
Dun & Bradstreet (1998): Who Owns Whom. North & South America. -- High Wycombe, UK: Dun & Bradstreet Ltd.   
Feldman, Maryann P. (1994a): The Geography of Innovation. Boston: Kluwer Academic Publishers.

Feldman, Maryann P. (1994b): “Knowledge complementarity and innovation.” Small Business Economics, 6(3):363-372.   
Frost, Tony S. (2001): “The geographic sources of foreign subsidiaries’ innovations.” Strategic Management Journal, 22(2):101-23.   
Glaeser, Edward, H. Kallal, Jose Scheinkman, and Andre Schleifer. (1992): “Growth of cities.” Journal of Political Economy, 100(6):1126-1152.   
Grossman, Gene, and Elhanan Helpman (1991): Innovation and Growth in the Global Economy. Cambridge, MA: MIT Press.   
Hicks, Diane, Tony Breitzman, Dominic Olivastro, and Kimberly Hamilton, (2001): “The changing composition of innovative activity in the US – a portrait based on patent analysis.” Research Policy, 30(4):681-703.   
Jacobs, Jane (1969): The Economy of Cities. New York: Random House.   
Jaffe, Adam B., Manuel Trajtenberg,, and Michael S. Fogarty (2002): “The meaning of patent citations: report on the NBER/Case Western Reserve survey of patentees.” In A.B. Jaffe and M. Trajtenberg, Patents, Citations, and Innovations: A Window on the Knowledge Economy. Cambridge: MIT Press, pp. 379-401.   
Jaffe, Adam B., Manuel Trajtenberg, and Rebecca Henderson, (1993): "Geographic knowledge spillovers as evidenced by patent citations." Quarterly Journal of Economics, 108(3):577-98.   
Katz, Ethan (2001): “Bias in conditional and unconditional fixed effects logit.” Political Analysis, 9(4):379-384.   
Krugman, Paul R. (1991) Geography and Trade. Cambridge, MA: MIT Press, 1991.   
Manski, Charles F. (2000): “Economic analysis of social interaction.” Journal of Economic Perspectives, 14:115-136.   
Marshall, Alfred. (1890): Principles of Economics, London: Macmillan.   
Romer, Paul M. (1990): "Endogenous technological change." Journal of Political Economy, 98(5, pt. 2):S71-S102.   
Thompson, Peter, and Melanie Fox-Kean (2005): “Patent citations and the geography of knowledge spillovers: a reassessment.” American Economic Review, 95(1):450-460.   
US Census (2004): “Annual geographic mobility rates, by type of movement: 1947-2001. www.census.gov/population/socdemo/migration/tab-a-1.txt. Accessed March 15, 2004.