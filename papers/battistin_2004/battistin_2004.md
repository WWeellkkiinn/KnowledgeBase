# The Impact of Measurement Error on Evaluation Methods Based on Strong Ignorability∗

Erich Battistin Institute for Fiscal Studies

Andrew Chesher University College London and Cemmap

13th February 2004

# Abstract

When selection bias can purely be attributed to observables, several estimators have been discussed in the literature to estimate the average effect of a binary treatment or policy on a scalar outcome. Identification typically exploits the unconfoundedness of the treatment, which is verified if the participation status is independent of potential outcomes conditional on observable covariates. Assuming unconfoundedness, the average effect of the treatment can be estimated by differencing within subpopulation averages of treated and untreated units, or by propensity score methods under an additional condition on the support of the covariates exploited. The latter condition, together with unconfoundedness, makes participation into the treatment group strongly ignorable, as defined by Rosenbaum and Rubin (1983). This paper studies the impact of covariate measurement error on commonly used evaluation methods based on strong ignorability. An approximate expression for the measurement error bias is derived, and conditions are discussed for this to be zero. A bias correction procedure is also presented, which uses non-parametric estimates of functionals of the distribution of observed covariates.

Keywords: potential outcomes, small sigma asymptotics, treatment effects

# Contents

1 Introduction 3

2 Identification of treatment effects in the absence of measurement error 4

2.1 Parameters of interest . . . 4   
2.2 Ignorable assignment . . . . 4   
2.3 Identification results . . 5

2.3.1 Effect on the population . . . 6   
2.3.2 Effect on the treated . . . . 7   
2.3.3 Alternative estimation strategies . . . . 7

2.4 A parametric example . . 8

3 Covariate measurement error 9

3.1 Approximate distributions . . 9   
3.2 Approximate expectations . . 10   
3.3 Remarks . . . 11

4 The effect of using mismeasured regressors 11

4.1 Effect on the population . . . 11   
4.2 Effect on the treated . . 12   
4.3 A parametric example (continued) 1 3

5 A bias correction procedure 14

5.1 Effect on the treated . . 14   
5.2 A parametric example (continued) . . 1 5

6 More than one covariate, just one with error 15

7 Example 15

7.1 Approximation to the bias . . . 1 6   
7.2 Exact expression for the bias 16   
7.3 Bias correction 17

8 Conclusions 18

# 1 Introduction

When evaluating the effect of a programme it is common to impose the restriction that, conditional on a set of observable variables, potential outcomes and a participation indicator are independently distributed. Under this restriction and a support condition which together constitute the strong ignorability restriction of Rosenbaum and Rubin (1983), the average effect of treatment on the treated and the average treatment effect are identified. Estimation typically proceeds by propensity score matching or by comparing weighted averages of outcomes for participants and nonparticipants.

In practice the conditioning variables, X, with respect to which strong ignorability are maintained may be observed with error, that is, instead of realisations of X one observes realisations of $Z \equiv g ( X , U )$ where U is a vector of measurement errors. This paper explores the impact of such covariate measurement error on commonly used programme evaluation methods such as propensity score matching. The strategy we employ is as follows.

When the strong ignorability restriction holds there are correspondences which identify parameters of interest (e.g. the average effect of treatment on the treated) as functionals of the distribution of observable outcomes and covariates. Let $F _ { Y X }$ denote this distribution. In the absence of measurement error data are informative about $F _ { Y X \cdot \mathrm { ~ A ~ } }$ parameter θ is identified by a correspondence, $\theta  \mathcal { H } ( F _ { Y X } )$ and H is termed an identifying functional. Matching, and other estimators employed in practice, ${ \hat { \theta } } ,$ are analogue estimators obtained by applying identifying functionals to an estimate of the distribution of observable outcomes and covariates, that is $ { \hat { \theta } } \equiv \mathcal { H } (  { \hat { F } } _ { Y X } )$ .

When measurement error is present data are informative about the distribution of observable outcomes and measurement error contaminated covariates. Let $F _ { Y Z }$ denote this distribution. If the presence of measurement error is ignored, or not perceived, then parameters of interest are estimated using realizations of $( Y , Z )$ as if they were realizations of $( Y , X )$ , that is $\hat { \theta } \equiv \mathcal { H } ( \hat { F } _ { Y Z } )$ . Under quite weak conditions $\hat { \theta } \overset { p } {  } \mathcal { H } ( F _ { Y Z } )$ .

We study the properties of $\mathcal { H } ( F _ { Y Z } )$ and its relationship to $\mathcal { H } ( F _ { Y X } )$ , in particular $\Delta \equiv \mathcal { H } ( F _ { Y Z } ) - \mathcal { H } ( F _ { Y X } )$ . The value of $\Delta$ depends on details of the features of the distribution of $Y , X$ and U and a case by case analysis is required if exact results are to be obtained. We are interested in the generic impacts of measurement error and obtain information about these by considering the local effects of measurement error, that is by considering the value of $\Delta$ when $Z = g ( X , \sigma U )$ and σ is small.

We consider the case in which $Z = X + \sigma U$ and U and X are independently distributed. Under conditions to be stated, for functionals H of interest,

$$
\mathcal {H} (F _ {Y Z}) = \mathcal {H} (F _ {Y X}) + \sigma^ {2} \mathcal {H} ^ {*} (F _ {Y X}) + o (\sigma^ {2})
$$

where lim $_ { 1 _ { \sigma }  0 } ( \sigma ^ { - 2 } o ( \sigma ^ { 2 } ) ) = 0$ . The functional $\mathcal { H } ^ { \ast }$ is obtained using the method employed in Chesher (1991). Properties of this functional are explored to shed light on the “first order” impact of measurement error and the way in which this depends upon features of $F _ { Y X }$ .

Arguing as in Chesher and Schluter (2002) in the cases studied here $\mathcal { H } ^ { * } ( F _ { Y X } ) =$ $\mathcal { H } ^ { \ast } ( F _ { Y Z } ) + o ( \sigma ^ { 2 } )$ and so there is

$$
\mathcal {H} (F _ {Y Z}) = \mathcal {H} (F _ {Y X}) + \sigma^ {2} \mathcal {H} ^ {*} (F _ {Y Z}) + o (\sigma^ {2}).
$$

Since data are informative about $F _ { Y Z }$ it may be possible to estimate $\mathcal { H } ^ { \ast } ( F _ { Y Z } )$ and so gain a view of the likely first order effect of measurement error at conjectured values of the measurement error variance $\sigma ^ { 2 }$ .

The method is applied in a set of simple cases in which the exact impact of measurement error can be calculated and the quality of the “small $\sigma ^ { \mathfrak { n } }$ approximation is investigated.

# 2 Identification of treatment effects in the absence of measurement error

Let $( Y _ { 1 } , Y _ { 0 } )$ be the potential outcomes from participating and not participating, respectively, and let D be the participation status. The causal effect of the program is then defined as the difference between the two potential outcomes, $\beta = Y _ { 1 } - Y _ { 0 }$ , which is not observable since being exposed to (denied) the program reveals Y1 (Y0) but conceals the other potential outcome (Holland, 1986).

# 2.1 Parameters of interest

Average effect of the treatment in the population $( \beta _ { p } )$ and average effect of the treatment on the treated $( \beta _ { t } )$

$$
{\beta_ {p}} = {E _ {Y _ {1}} (Y _ {1}) - E _ {Y _ {0}} (Y _ {0}),}
$$

$$
\beta_ {t} = E _ {Y _ {1} | D} (Y _ {1} | 1) - E _ {Y _ {0} | D} (Y _ {0} | 1).
$$

The latter parameter is of interest if one wishes to evaluate the effect of the treatment on the population that is likely to take up the treatment (Heckman et al., 1999).

# 2.2 Ignorable assignment

Selection bias is caused by the fact that program participants $( D = 1 )$ differ from non-participants $( D = 0 )$ with respect to characteristics that affect potential outcomes. It follows that, because of differences in the composition, the two groups would not have the same outcomes even in the absence of the program (see Heckman et al., 1999).

When differences in the composition of participants and non-participants can purely be attributed to observable characteristics, one can control for the selection bias by including in the model the appropriate conditioning variables. Under these circumstances, identification of the mean impact rests on the existence of an observable vector of individual characteristics X such that strong ignorability with respect to X (SI-X) holds true (Rosenbaum and Rubin, 1983). This corresponds to say that the following two conditions are jointly satisfied

$$
\left(Y _ {0}, Y _ {1}\right) \bot D | X, \tag {1}
$$

$$
\operatorname{Var} (D | X) > 0. \tag {2}
$$

According to (1), it is as if individuals were randomly assigned to the treatment with a probability depending on X provided that such probability is nondegenerate at each value of these variables.1 In a randomized experiment the latter condition is satisfied by design, since each individual has a positive probability of being randomized into or out of the program. In the case of observational studies, the common support assumption (2) is instead required (see Heckman et al., 1998, and Lechner, 2001).

Since units presenting the same characteristics X have a common probability to enter the program, then an operational rule to obtain an ex post experimentallike data set is to match participants to non-participants on such probability (the so called propensity score), whose dimension is invariant with respect to the dimension of X. In fact, it can be proved (Theorem 3 by Rosenbaum and Rubin, 1983) that if SI-X is satisfied, then the treatment assignment is strongly ignorable also given the propensity score.

In terms of distribution functions, SI-X implies

$$
F _ {Y _ {i} | D X} (y _ {i} | d, x) = F _ {Y _ {i} | X} (y _ {i} | x), \qquad i = 0, 1
$$

where $d \in \{ 0 , 1 \}$ . Condition (1) is actually stronger than required to get identification of causal effects, since as discussed in the next section the following mean independence condition

$$
E _ {Y _ {i} | D X} (Y _ {i} | d, x) = E _ {Y _ {i} | X} (Y _ {i} | x), \qquad i = 0, 1
$$

would be sufficient.2

# 2.3 Identification results

Identification results for the parameters of interest are reviewed in what follows (see Heckman et al., 1999, and Imbens, 2004). Throughout this section, = will imply that SI-X (or mean independence together with the common support condition) is required for the result to hold.

Assuming SI-X, the average effect of the treatment can be estimated by matching, differencing within subpopulation averages of treated and untreated units, or by propensity score methods. It is shown below that the asymptotic behavior of these estimators can be studied by looking at the quantities (3) and (4) if the target parameter is $\beta _ { p } ,$ , or (5) if the target parameter is $\beta _ { t }$ .

# 2.3.1 Effect on the population

Let $Y = Y _ { 0 } + D \beta$ be the observed outcome and let $e _ { X } ( x ) = { \cal E } _ { D | X } ( D | x )$ . It follows that

$$
E _ {Y _ {1}} (Y _ {1}) = \int E _ {Y _ {1} | X} (Y _ {1} | x) f _ {X} (x) d x,
$$

$$
\stackrel {a} {=} \int E _ {Y _ {1} | D X} (Y _ {1} | 1, x) f _ {X} (x) d x, \tag {3}
$$

$$
= \int \frac {E _ {Y D | X} (Y D | x)}{e _ {X} (x)} f _ {X} (x) d x,
$$

and

$$
E _ {Y _ {0}} (Y _ {0}) = \int E _ {Y _ {0} | X} (Y _ {0} | x) f _ {X} (x) d x,
$$

$$
\stackrel {a} {=} \int E _ {Y _ {0} | D X} (Y _ {0} | 0, x) f _ {X} (x) d x, \tag {4}
$$

$$
= \int \frac {E _ {Y D | X} (Y [ 1 - D ] | x)}{1 - e _ {X} (x)} f _ {X} (x) d x,
$$

with the last equalities of each expression following from

$$
E _ {Y D | X} (Y D | x) = E _ {Y _ {1} | D X} (Y _ {1} | 1, x) e _ {X} (x),
$$

$$
E _ {Y D | X} (Y [ 1 - D ] | x) = E _ {Y _ {0} | D X} (Y _ {0} | 0, x) [ 1 - e _ {X} (x) ].
$$

The quantities above can be consistently estimated by their sample analogues (see Horvitz and Thompson, 1952, Rosenbaum, 1987, Hahn, 1998, and Hirano et al., 2003)

$$
\hat {E} _ {Y _ {1}} (Y _ {1}) = \frac {1}{n} \sum_ {i = 1} ^ {n} \frac {d _ {i}}{e _ {X} (x _ {i})} y _ {i},
$$

$$
\hat {E} _ {Y _ {0}} (Y _ {0}) = \frac {1}{n} \sum_ {i = 1} ^ {n} \frac {1 - d _ {i}}{1 - e _ {X} (x _ {i})} y _ {i},
$$

so that

$$
\hat {\beta} _ {p} = \hat {E} _ {Y _ {1}} (Y _ {1}) - \hat {E} _ {Y _ {0}} (Y _ {0}).
$$

The quantity $e _ { X } ( x )$ represents the conditional probability of participation given the observed characteristics X, which is often referred to in the literature as the propensity score (Rosenbaum and Rubin, 1983). The interpretation of the weighting procedure is appealing: participants and non-participants are given more (less) weight depending on whether they are under (over) represented in the population with respect to their characteristics X. Regardless of the number of X variables, weights can be defined using the propensity score which is always a scalar.

# 2.3.2 Effect on the treated

Along the same lines of what discussed in the previous section,3 it follows that

$$
\begin{array}{l} E _ {Y _ {0} | D} (Y _ {0} | 1) = \int E _ {Y _ {0} | D X} (Y _ {0} | 1, x) f _ {X | D} (x | 1) d x, \\ \stackrel {a} {=} \int E _ {Y _ {0} | D X} (Y _ {0} | 0, x) f _ {X | D} (x | 1) d x, \tag {5} \\ = \int E _ {Y _ {0} | D X} (Y _ {0} | 0, x) \frac {e _ {X} (x) f _ {X} (x)}{P (D = 1)} d x, \\ = \int \frac {E _ {Y D | X} (Y [ 1 - D ] | x)}{1 - e _ {X} (x)} \frac {e _ {X} (x)}{P (D = 1)} f _ {X} (x) d x. \\ \end{array}
$$

Therefore, a consistent estimate of the treatment effect can be obtained from

$$
\hat {E} _ {Y _ {1} | D} (Y _ {1} | 1) = \frac {1}{n _ {1}} \sum_ {i = 1} ^ {n} d _ {i} y _ {i},
$$

$$
\hat {E} _ {Y _ {0} | D} (Y _ {0} | 1) = \frac {1}{n _ {1}} \sum_ {i = 1} ^ {n} \frac {(1 - d _ {i}) e _ {X} (x _ {i})}{1 - e _ {X} (x _ {i})} y _ {i},
$$

and

$$
\hat {\beta} _ {t} = \hat {E} _ {Y _ {1} | D} (Y _ {1} | 1) - \hat {E} _ {Y _ {0} | D} (Y _ {0} | 1).
$$

# 2.3.3 Alternative estimation strategies

Estimation strategies alternative to the ones presented above can be obtained by using the empirical analogues of the distributions $f _ { X } ( x )$ and $f _ { X \mid D } ( x | 1 )$ combined with an estimator of the conditional expectation $E _ { Y _ { d } | D X } ( Y _ { d } | d , x ) , \ d \in \{ 0 , 1 \}$ . This yields the generalized matching estimators

$$
\hat {E} _ {Y _ {1}} (Y _ {1}) = \frac {1}{n} \sum_ {i = 1} ^ {n} \hat {E} _ {Y _ {1} | D X} (Y _ {1} | 1, x _ {i}),
$$

$$
\hat {E} _ {Y _ {0}} (Y _ {0}) = \frac {1}{n} \sum_ {i = 1} ^ {n} \hat {E} _ {Y _ {0} | D X} (Y _ {0} | 0, x _ {i}),
$$

$$
\hat {E} _ {Y _ {0} | D} (Y _ {0} | 1) = \frac {1}{n _ {1}} \sum_ {i = 1} ^ {n _ {1}} \hat {E} _ {Y _ {0} | D X} (Y _ {0} | 0, x _ {i}),
$$

for the quantities in (3), (4) and (5), respectively. Conditional expectations in the previous expressions can be estimated semi-non-parametrically following one of the several methods suggested in the literature (see Imbens, 2004, for a review).

It is worth noting that any “X-adjusted” estimator is asymptotically equivalent to an ${ } ^ { \mathfrak { s } } e _ { X } ( x )$ -adjusted” estimator. This result straightforwardly follows from the fact that $X \bot D | e _ { X } ( x )$ , that is from the fact that the propensity score is a balancing score for X (see Theorem 2 by Rosenbaum and Rubin, 1983, and Fr¨olich, 2003). For example, by using this property and the law of iterated expectations one would get

$$
\begin{array}{l} \int E _ {Y _ {0} \mid D e _ {X}} (Y _ {0} | 0, e) f _ {e _ {X} \mid D} (e \mid 1) d e, \tag {6} \\ = \int \int E _ {Y _ {0} | D X} (Y _ {0} | 0, x) f _ {X | D e _ {X}} (x | 0, e) f _ {e _ {X} | D} (e | 1) d x d e, \\ = \int \int E _ {Y _ {0} | D X} (Y _ {0} | 0, x) f _ {X | D e _ {X}} (x | 1, e) f _ {e _ {X} | D} (e | 1) d x d e, \\ = \int E _ {Y _ {0} | D X} (Y _ {0} | 0, x) f _ {X | D} (x | 1) d x, \\ \end{array}
$$

which corresponds to (5). The empirical analogue of (6) defines the propensity score matching estimator of $\beta _ { t }$ (see, for example, Heckman et al., 1999). It follows that this class of estimators is also covered by our discussion.

# 2.4 A parametric example

To fix ideas, consider the following parametric regression

$$
y _ {i} = \alpha + \beta d _ {i} + \delta x _ {i} + \varepsilon_ {i} \tag {7}
$$

for the case of homogeneous returns to the treatment $( \beta _ { i } = \beta )$ and $E ( \varepsilon _ { i } | d _ { i } , x _ { i } ) =$ 0. If participation is SI-X, then ordinary least squares provide a consistent estimate of $\beta .$ .

By partialing out the effect of D from (7)

$$
E (y _ {i} | d _ {i}) = \alpha + \beta d _ {i} + \delta E (x _ {i} | d _ {i}),
$$

it follows that

$$
\widetilde {y} _ {i} = \delta \widetilde {x} _ {i} + \varepsilon_ {i},
$$

where $\widetilde { y } _ { i } = y _ { i } - E \left( y _ { i } | d _ { i } \right)$ and $\widetilde x _ { i } = x _ { i } - E ( x _ { i } | d _ { i } )$ . A consistent estimate of $\delta$ can be obtained from the last regression, and identification of $\beta$ follows from

$$
\beta = [ E (y _ {i} | 1) - E (y _ {i} | 0) ] - \delta [ E (x _ {i} | 1) - E (x _ {i} | 0) ].
$$

Accordingly, the effect $\beta$ is identified by the raw difference of mean outcomes net of the composition difference with respect to $X$ scaled by $\delta . ^ { 4 }$

# 3 Covariate measurement error

In what follows identification results for $\beta _ { p }$ and $\beta _ { t }$ are discussed when the sample analogues of the expressions in (3), (4) and (5) are computed unknowingly observing $Z$ in place of X. Let $Z = X + U$ with $U \perp ( X , D , Y )$ and $E [ U ] = 0$ , $E [ U ^ { 2 } ] = \sigma ^ { 2 }$ . For the moment regard X as scalar continuously distributed on the real line.

Two things are worth noting. First, measurement error U is such that $Z$ and X have the same support, and this coincides with the real line. Second, the common support of the Z distributions is not modified by the measurement error and coincides with the common support of the X distributions (i.e. the real line). If (2) is verified, then $V a r ( D | Z ) > 0$ .

In what follows we show that measurement error bias arises in the estimation of $\beta _ { p }$ and $\beta _ { t }$ since SI-X does not imply SI-Z. In other words, if participants and non-participants are balanced with respect to $Z ,$ the two groups are not balanced with respect to the distribution of X so that the condition $X \bot D | Z$ fails to hold.5 In what follows, conditions are derived for the measurement bias to be zero (Conditions 1-3 below).

# 3.1 Approximate distributions

Consider $F _ { Y \mid D Z }$ . Direct application of the approximation for conditional distribution functions when covariates are measured with error, given in Chesher (1991), regarding D as measured without error and X as measured with error, and using the SI-X assumption, gives6

$$
F _ {Y | D Z} (y | d, z) \simeq F _ {Y | X} (y | z) + \sigma^ {2} F _ {Y | X} ^ {\prime} (y | z) \left(\frac {f _ {X | D} ^ {\prime} (z | d)}{f _ {X | D} (z | d)}\right) + \frac {\sigma^ {2}}{2} F _ {Y | X} ^ {\prime \prime} (y | z),
$$

where recall $Y \equiv ( Y _ { 0 } , Y _ { 1 } )$ and $y \equiv ( y _ { 0 } , y _ { 1 } )$ and $A \simeq B$ indicates $A = B + o ( \sigma ^ { 2 } ) . ^ { 7 }$

$$
{f _ {X | D Z} (x | d, z)} = {\frac {f _ {D | X} (d | x)}{f _ {D | Z} (d | z)} f _ {X | Z} (x | z),}
$$

$$
{f _ {D | Z} (d | z)} = {\int f _ {D | X} (d | x) f _ {X | Z} (x | z) d x,}
$$

it follows that

$$
f _ {X | D Z} (x | d, z) = f _ {X | Z} f (x | z) \Leftrightarrow \frac {f _ {D | X} (d | x)}{\int f _ {D | X} (d | x) f _ {X | Z} (x | z) d x} = 1,
$$

which is satisfied if X⊥D.

6Throughout this paper, we will assume that the conditions stated in Chesher (1991) are satisfied.

7For vector X and using the Einsteinian summation convention (summation over repeated raised and lowered indices) there is

$$
F _ {Y | D Z} (y | d, z) \simeq F _ {Y | X} (y | z) + \sigma_ {i j} F _ {Y | X} ^ {i} (y | z) \left(\frac {f _ {X | D} ^ {j} (z | d)}{f _ {X | D} (z | d)}\right) + \frac {\sigma_ {i j}}{2} F _ {Y | X} ^ {i j} (y | z),
$$

where $Z _ { k } = X _ { k } + U _ { k }$ and $E [ U _ { i } U _ { j } ] = \sigma _ { i j }$ .

Note all the above is for the joint distribution of $Y _ { 1 }$ and $Y _ { 0 }$ . We have for the marginal distribution of $Y _ { i } , i \in \{ 0 , 1 \}$

$$
F _ {Y _ {i} | D Z} (y _ {i} | d, z) \simeq F _ {Y _ {i} | X} (y _ {i} | z) + \sigma^ {2} F _ {Y _ {i} | X} ^ {\prime} (y _ {i} | z) \left(\frac {f _ {X | D} ^ {\prime} (z | d)}{f _ {X | D} (z | d)}\right) + \frac {\sigma^ {2}}{2} F _ {Y _ {i} | X} ^ {\prime \prime} (y _ {i} | z).
$$

Thus, locally, Y is SI-Z if

$$
F _ {Y _ {i} | X} ^ {\prime} (y _ {i} | z) \left(\frac {f _ {X | D} ^ {\prime} (z | 1)}{f _ {X | D} (z | 1)} - \frac {f _ {X | D} ^ {\prime} (z | 0)}{f _ {X | D} (z | 0)}\right) = 0, \qquad i \in \{0, 1 \}
$$

for which a sufficient condition is either of the following

Condition 1 $F _ { Y _ { i } | X } ^ { \prime } ( y _ { i } | z ) = 0$ for all values of its arguments.

Condition 2 For all values of z

$$
\frac {f _ {X | D} ^ {\prime} (z | 1)}{f _ {X | D} (z | 1)} = \frac {f _ {X | D} ^ {\prime} (z | 0)}{f _ {X | D} (z | 0)}.
$$

The former condition virtually requires Y to be independent of X, which is not an interesting case. The latter condition requires $X \perp D$ which is also uninteresting (the propensity score would be uninformative under this condition).8

# 3.2 Approximate expectations

Replacing F by f gives the approximation for density functions (if Y is continuously distributed), as follows (see Chesher, 1991)

$$
f _ {Y _ {i} | D Z} (y _ {i} | d, z) \simeq f _ {Y _ {i} | X} (y _ {i} | z) + \sigma^ {2} f _ {Y _ {i} | X} ^ {\prime} (y _ {i} | z) \left(\frac {f _ {X | D} ^ {\prime} (z | d)}{f _ {X | D} (z | d)}\right) + \frac {\sigma^ {2}}{2} f _ {Y _ {i} | X} ^ {\prime \prime} (y _ {i} | z).
$$

Replacing F by E gives the result for regression functions, as follows

$$
E _ {Y _ {i} | D Z} (Y _ {i} | d, z) \simeq E _ {Y _ {i} | X} (Y _ {i} | z) + \sigma^ {2} E _ {Y _ {i} | X} ^ {\prime} (Y _ {i} | z) \left(\frac {f _ {X | D} ^ {\prime} (z | d)}{f _ {X | D} (z | d)}\right) + \frac {\sigma^ {2}}{2} E _ {Y _ {i} | X} ^ {\prime \prime} (Y _ {i} | z).
$$

As above, mean independence given Z holds if

$$
E _ {Y _ {i} | X} ^ {\prime} (y _ {i} | z) \left(\frac {f _ {X | D} ^ {\prime} (z | 1)}{f _ {X | D} (z | 1)} - \frac {f _ {X | D} ^ {\prime} (z | 0)}{f _ {X | D} (z | 0)}\right) = 0, \qquad i \in \{0, 1 \}.
$$

Accordingly, either Condition 2 or the following

Condition 3 $E _ { Y _ { i } | X } ^ { \prime } ( y _ { i } | z ) = 0$ for all values z.

are sufficient for mean independence given Z to hold.9

# 3.3 Remarks

Results in this section point out that groups of individuals balanced with respect to the distribution of $Z$ are not balanced with respect to the distribution of $X$ , so that the condition $X \bot D | Z$ fails to hold. Along the same lines, it straightforwardly follows that the propensity score based on Z is not a balancing score for $X$ , so that the condition $X \perp D | e _ { Z }$ is not satisfied. Accordingly, by computing any propensity score adjustment unknowingly based on $Z$ in place of $X$ one will get biased estimates of the treatment effect.

However, it is worth noting that, regardless $o f$ the nature of the measurement error $U , e _ { Z }$ is a balancing score for Z, that is the condition $Z \perp D | e _ { Z }$ is satisfied. This results holds whatever the nature of the error is and it is a straightforward implication of Theorem 2 by Rosenbaum and Rubin (1983). For example, along the same lines of what derived in (6), it can be shown that

$$
\begin{array}{l} \int E _ {Y _ {0} | D e _ {Z}} (Y _ {0} | 0, e) f _ {e _ {Z} | D} (e | 1) d e, \\ = \int E _ {Y _ {0} | D Z} (Y _ {0} | 0, z) f _ {Z | D} (z | 1) d z. \\ \end{array}
$$

In the next section, we will be interested in studying what happens to alternative estimators of the quantities (3), (4) and (5) when $Z$ is used instead of X. The implication of $Z \perp D | e _ { Z }$ stated in the last expression will allow us to develop an unified approach to studying the asymptotic behaviour of these estimators.

# 4 The effect of using mismeasured regressors

The measurement error bias is derived for $\beta _ { p }$ (Proposition 1) and $\beta _ { t }$ (Proposition 2). The proof of Proposition 1 is omitted because similar in spirit to the proof of Proposition 2, which is instead reported in the Appendix.10

# 4.1 Effect on the population

By using Z in place of X, one will obtain consistent estimators of

$$
A _ {i} = \int_ {- \infty} ^ {\infty} E _ {Y _ {i} | D Z} (Y _ {i} | i, z) f _ {Z} (z) d z, \qquad i \in \{0, 1 \}
$$

which correspond to (3) and (4) when Z is used instead of X. Limits of integration $( - \infty , \infty )$ will be suppressed in what follows.

Proposition 1 If SI-X holds and

$$
\lim _ {z \to \pm \infty} E _ {Y _ {i} | X} (Y _ {i} | z) f _ {X} ^ {\prime} (z) = 0,
$$

$$
\lim _ {z \to \pm \infty} E _ {Y _ {i} | X} ^ {'} (Y _ {i} | z) f _ {X} (z) = 0,
$$

neglecting terms which are $o \big ( \sigma ^ { 2 } \big )$ there is the following expression for $A _ { i }$

$$
\boxed {A _ {i} \simeq E _ {Y _ {i}} [ Y _ {i} ] + \sigma^ {2} B _ {i},}
$$

where

$$
{B _ {i}} = {\int E _ {Y _ {i} | X} ^ {'} (Y _ {i} | z) \frac {f _ {X | D} ^ {'} (z | i)}{f _ {X | D} (z | i)} f _ {X} (z) d z}
$$

$$
+ \int E _ {Y _ {i} | X} ^ {\prime \prime} (Y _ {i} | x) f _ {X} (z) d z. \quad \blacksquare
$$

Accordingly, the estimated effect in the population differs from the true effect (at the second order for σ) by means of the following factor

$$
\begin{array}{l} {\Delta (\beta_ {p})} = {\sigma^ {2} (B _ {1} - B _ {0})} \\ = \int \left[ E _ {Y _ {1} | D X} ^ {\prime} (Y _ {1} | 1, z) \frac {f _ {X | D} ^ {\prime} (z | 1)}{f _ {X | D} (z | 1)} - E _ {Y _ {0} | D X} ^ {\prime} (Y _ {0} | 0, z) \frac {f _ {X | D} ^ {\prime} (z | 0)}{f _ {X | D} (z | 0)} \right] f _ {X} (z) d z \\ + \int \left[ E _ {Y _ {1} | D X} ^ {\prime \prime} (Y _ {1} | 1, x) - E _ {Y _ {0} | D X} ^ {\prime \prime} (Y _ {0} | 0, x) \right] f _ {X} (z) d z. \\ \end{array}
$$

# 4.2 Effect on the treated

Under SI-X there is

$$
E _ {Y _ {0} | D} [ Y _ {0} | 1 ] = \int E _ {Y _ {0} | D X} (Y _ {0} | 0, x) \frac {f _ {X | D} (x | 1)}{f _ {X | D} (x | 0)} f _ {X | D} (x | 0) d x.
$$

Someone unknowingly observing Z in place of X and computing the sample analogue of this expression will obtain an estimator of

$$
A = \int E _ {Y _ {0} | D Z} (Y _ {0} | 0, z) f _ {Z | D} (z | 1) d z.
$$

Proposition 2 If SI-X holds and

$$
\lim _ {z \to \pm \infty} E _ {Y _ {0} | D X} (Y _ {0} | 0, z) f _ {X | D} ^ {\prime} (z | 1) = 0,
$$

$$
\lim _ {z \to \pm \infty} E _ {Y _ {0} | D X} ^ {\prime} (Y _ {0} | 0, z) f _ {X | D} (z | 1) = 0,
$$

neglecting terms which are $o \big ( \sigma ^ { 2 } \big )$ there is the following expression for A

$$
\boxed {A \simeq E _ {Y _ {0} | D} [ Y _ {0} | 1 ] + \sigma^ {2} B,} \tag {8}
$$

where

$$
{ B } { = } { \int E _ { Y _ { 0 } | D X } ^ { \prime } ( Y _ { 0 } | 0 , z ) \left( \frac { f _ { X | D } ^ { \prime } ( z | 0 ) } { f _ { X | D } ( z | 0 ) } \right) f _ { X | D } ( z | 1 ) d z }
$$

$$
+ \int E _ {Y _ {0} | D X} ^ {\prime \prime} (Y _ {0} | 0, z) f _ {X | D} (z | 1) d z.
$$

Accordingly, the estimated effect differs from the true effect in the population by means of the following term

$$
\Delta (\beta_ {t}) = \sigma^ {2} B.
$$

Consider the case in which $f _ { X | D } ( z | 1 ) = f _ { X | D } ( z | 0 )$ . Then the first term in B becomes

$$
\int E _ {Y _ {0} | D X} ^ {\prime} (Y _ {0} | 0, z) f _ {X | D} ^ {\prime} (z | 0) d z = \int E _ {Y _ {0} | D X} ^ {\prime} (Y _ {0} | 0, z) f _ {X | D} ^ {\prime} (z | 1) d z,
$$

$$
{ = } { - \int E _ { Y _ { 0 } | D X } ^ { \prime \prime } ( Y _ { 0 } | 0 , z ) f _ { X | D } ( z | 1 ) d z , }
$$

the second line following on integrating by parts. Clearly in this case $B = 0$ , which is as it should be.

# 4.3 A parametric example (continued)

Using the parametric example introduced above, it is easy to show that measurement error in X will make ordinary least squares estimates biased for $\beta .$ . In fact, classical measurement error in X implies that using Z as a proxy for X will partially, but only partially, control for the confounding effects of X on the estimation of $\beta$ (Wickens, 1972). Measurement error in X biases not only δ (which is a nuisance parameter for the problem), but more importantly biases also $\beta$ (unless D and X are not correlated, which is not an interesting case).

Since $z _ { i } = x _ { i } + u _ { i } . $ , the estimation of δ based on

$$
\widetilde {y} _ {i} = \delta \widetilde {z} _ {i} + v _ {i}
$$

features the usual attenuation bias, so that the following parameter

$$
\frac {\sigma_ {x} ^ {2}}{\sigma_ {x} ^ {2} + \sigma^ {2}} \delta
$$

is estimated in place of δ. Accordingly

$$
[ E (y _ {i} | 1) - E (y _ {i} | 0) ] - \delta [ E (x _ {i} | 1) - E (x _ {i} | 0) ] \frac {\sigma_ {x} ^ {2}}{\sigma_ {x} ^ {2} + \sigma^ {2}} \neq \beta .
$$

Because of the the measurement error $U ,$ the difference in raw means for $X$ is only partially ‘washed out’ from the difference in raw means for Y , resulting in biased estimates for the effect $\beta .$ . Note that Condition 3 here would be satisfied if $\delta = 0$ .

# 5 A bias correction procedure

The most common solution to the bias introduced by the measurement error in linear regression models is to exploit instrumental variables. However, it is well known that they do not yield consistent estimators of the parameters of interest in non-linear models (see, for example, Hausman et $a l .$ , 1995).

This section is along the same lines of what discussed in Chesher (2000). A method is proposed for obtaining estimates of the treatment effects which are purged of the major part of the effect of the measurement error. The method uses a quantity constructed from non-parametric estimates of functionals of the distribution of observed covariates Z. It follows that our procedure exploits nothing but the error contaminated data and does not require any functional assumptions on the regression of Y on D and X nor additional information (such as instrumental variables or validation data).11

In what follows, we will discuss how our correction procedure works for $\beta _ { t }$ . In further work, we will also apply the same correction to $\beta _ { p }$ .

# 5.1 Effect on the treated

Since X can be replaced by Z in expressions $\left( \mathrm { e . g . ~ } B \right)$ multiplied by $\sigma ^ { 2 }$ without altering the order of the approximation error we have

$$
\boxed {A \simeq E _ {Y _ {0} | D} [ Y _ {0} | 1 ] + \sigma^ {2} B ^ {*},}
$$

where

$$
\begin{array}{l} {B ^ {*}} = {\int E _ {Y _ {0} | D Z} ^ {\prime} (Y _ {0} | 0, z) \left(\frac {f _ {Z | D} ^ {\prime} (z | 0)}{f _ {Z | D} (z | 0)}\right) f _ {Z | D} (z | 1) d z} \\ + \int E _ {Y _ {0} | D Z} ^ {\prime \prime} (Y _ {0} | 0, z) f _ {Z | D} (z | 1) d z. \\ \end{array}
$$

This corresponds to what derived in (8) when X is replaced by Z. As the last expression can be rearranged to get

$$
\int \left[ E _ {Y _ {0} | D Z} ^ {\prime} (Y _ {0} | 0, z) \frac {d}{d z} \log f _ {Z | D} (z | 0) + E _ {Y _ {0} | D Z} ^ {\prime \prime} (Y _ {0} | 0, z) \right] f _ {Z | D} (z | 1) d z,
$$

it follows that $B ^ { * }$ can be estimated by

$$
\hat {B} ^ {*} = \frac {1}{n _ {1}} \sum_ {i = 1} ^ {n} \frac {(1 - d _ {i}) e _ {Z} (z _ {i})}{1 - e _ {Z} (z _ {i})} b (z _ {i}),
$$

$$
{b (z _ {i})} = {E _ {Y _ {0} | D Z} ^ {\prime} (Y _ {0} | 0, z _ {i}) \frac {d}{d z} \log f _ {Z | D} (z _ {i} | 0) - E _ {Y _ {0} | D Z} ^ {\prime \prime} (Y _ {0} | 0, z _ {i}),}
$$

from available data.

To estimate metric estimati $E _ { Y _ { 0 } | D Z } ^ { \prime } ( Y _ { 0 } | 0 , z )$ and ssion $E _ { Y _ { 0 } | D Z } ^ { \prime \prime } ( Y _ { 0 } | 0 , z )$ do parametricr people with para- and $Y _ { 0 }$ $D = 0$

calculate first and second derivatives with respect to $Z .$ To estimate the remaining elements one can do nonparametric density estimation for the $D = 0$ group (see the discussion in Chesher, 2000). Alternatively one might have a parametric model for D given X in which case one could estimate that and then do nonparametric density estimation of $f _ { Z } ( z )$ and then use, e.g.

$$
\hat {f} _ {Z | D} (z | 0) = \frac {[ 1 - e _ {Z} (z _ {i}) ] \hat {f} _ {Z} (z)}{\hat {P} [ D = 0 ]}.
$$

# 5.2 A parametric example (continued)

It follows from (7) that

$$
E (Y | d, z) = \beta d + \delta z - \delta E (U | d, z),
$$

since $E ( \varepsilon _ { i } | d _ { i } , x _ { i } ) = 0$ . The last expression qualifies the bias induced by measurement error as an omitted variable problem. The regression of $Y$ on $D$ and $Z$ fails to identify the parameter of interest $\beta$ because the term $E ( U | d , z )$ is omitted from the regression. Chesher (2000) shows that the following approximation holds

$$
E (Y | d, z) \simeq \beta d + \delta z - \delta \sigma^ {2} g (d, z),
$$

where $g ( d , z )$ is a term that can be estimated from observed data (i.e. it is function of $Z$ and $D$ only). The augmented regression including the $g ( d , z )$ term can be used to get a ‘bias reduced’ estimate of $\beta .$ Note that, as long as $g ( d , z )$ is not linear in $Z$ (which would be true if $U$ was normally distributed), then $\sigma ^ { 2 }$ could also be estimated from observed data.

# 6 More than one covariate, just one with error

In the expressions above, differentiation is with respect to the error contaminated covariate and the density $f _ { X \mid D }$ becomes $f _ { X ^ { * } | X _ { * } D }$ where $X ^ { * }$ is the error contaminated covariate and $X _ { * }$ contains the remaining covariates.

# 7 Example

This example is artificial, but rather convenient. Throughout this section normality will be assumed for the error $U _ { ☉ }$ . Moreover, suppose that the regression function of $Y$ on X for the $D = 0$ group is linear (as in Rubin, 1977)

$$
E _ {Y _ {0} | D X} (Y _ {0} | 0, x) = \alpha_ {0} + \beta_ {0} x
$$

and that

$$
X | D = d \sim N (d \mu_ {1} + (1 - d) \mu_ {0}, d \lambda_ {1} ^ {2} + (1 - d) \lambda_ {0} ^ {2}),
$$

for $d \in \{ 0 , 1 \}$

Assume that $\beta _ { t }$ is of interest to the analyst. According to what presented in the previous section, we wish to approximate

$$
A = \int E _ {Y _ {0} | D Z} [ Y _ {0} | 0, z ] f _ {Z | D} (z | 1) d z,
$$

which is what people will unwittingly estimate if they ignore measurement error. Three quantities are derived for the example considered in this section: the approximation to the measurement error bias in Proposition 2 is in (9); the exact expression for this bias (that is, the expression in terms of the unobserved X) is in (10); finally, the bias resulting from our correction procedure is in (11).

# 7.1 Approximation to the bias

The approximation as derived above, that is the right hand side of (8), is as follows

$$
A _ {X} ^ {a} \equiv \alpha_ {0} + \beta_ {0} \mu_ {1} + \sigma^ {2} \int \left[ E _ {Y _ {0} | X} ^ {\prime} (Y _ {0} | z) \left(\frac {f _ {X | D} ^ {\prime} (z | 0)}{f _ {X | D} (z | 0)}\right) + E _ {Y _ {0} | X} ^ {\prime \prime} (Y _ {0} | z) \right] f _ {X | D} (z | 1) d z,
$$

where we stress the dependence from distributions and expectations involving X by writing $A _ { X } ^ { a }$ . Since

$$
E _ {Y _ {0} | D X} ^ {\prime} (Y _ {0} | 0, z) = \beta_ {0}
$$

$$
E _ {Y _ {0} | D X} ^ {\prime \prime} (Y _ {0} | 0, z) = 0
$$

$$
{\frac {f _ {X | D} ^ {\prime} (z | 0)}{f _ {X | D} (z | 0)}} = {- \frac {1}{\lambda_ {0} ^ {2}} (z - \mu_ {0}),}
$$

we have

$$
A _ {X} ^ {a} = \alpha_ {0} + \beta_ {0} \mu_ {1} - \beta_ {0} \frac {\sigma^ {2}}{\lambda_ {0} ^ {2}} (\mu_ {1} - \mu_ {0}),
$$

so that

$$
\boxed {b i a s \left(A _ {X} ^ {a}\right) = - \beta_ {0} \left(\mu_ {1} - \mu_ {0}\right) \frac {\sigma^ {2}}{\lambda_ {0} ^ {2}}.} \tag {9}
$$

Although the approximation $A _ { X } ^ { a }$ is not exact, the approximation error is of order $O ( \sigma ^ { 4 } )$ .12

# 7.2 Exact expression for the bias

The exact expression for A is as follows. First consider the expectation in the expression for A. We have, conditional on $D = 0$

$$
\left[ \begin{array}{l} X \\ Z \end{array} \right] | D = 0 \sim N \left(\left[ \begin{array}{l} \mu_ {0} \\ \mu_ {0} \end{array} \right], \left[ \begin{array}{c c} \lambda_ {0} ^ {2} & \lambda_ {0} ^ {2} \\ \lambda_ {0} ^ {2} & \lambda_ {0} ^ {2} + \sigma^ {2} \end{array} \right]\right),
$$

and so

$$
X | (Z \cap D = 0) \sim N \left(\mu_ {0} + \frac {\lambda_ {0} ^ {2}}{\lambda_ {0} ^ {2} + \sigma^ {2}} (z - \mu_ {0}), \lambda_ {0} ^ {2} - \frac {\lambda_ {0} ^ {4}}{\lambda_ {0} ^ {2} + \sigma^ {2}}\right).
$$

Therefore, for the expectation appearing in A there is (remember that $Y _ { 0 } \bot Z | X )$

$$
\begin{array}{l} E _ {Y _ {0} | D Z} (Y _ {0} | 0, z) = \int E _ {Y _ {0} | D Z X} (Y _ {0} | 0, z, x) f _ {X | Z D} (x | z, 0) d x, \\ = \int (\alpha_ {0} + \beta_ {0} x) f _ {X | Z D} (x | z, 0) d x, \\ { = } { \alpha _ { 0 } + \beta _ { 0 } \mu _ { 0 } + \frac { \beta _ { 0 } \lambda _ { 0 } ^ { 2 } } { \lambda _ { 0 } ^ { 2 } + \sigma ^ { 2 } } ( z - \mu _ { 0 } ) , } \\ \end{array}
$$

which exhibits the usual attenuation, and since $Z | D = 1 \sim N ( \mu _ { 1 } , \lambda _ { 1 } ^ { 2 } + \sigma ^ { 2 } )$

$$
A = \alpha_ {0} + \beta_ {0} \mu_ {0} + \frac {\beta_ {0} \lambda_ {0} ^ {2}}{\lambda_ {0} ^ {2} + \sigma^ {2}} (\mu_ {1} - \mu_ {0}),
$$

$$
= \alpha_ {0} + \beta_ {0} \mu_ {1} - \beta_ {0} (\mu_ {1} - \mu_ {0}) \frac {\sigma^ {2}}{\lambda_ {0} ^ {2} + \sigma^ {2}}.
$$

The final term gives the exact bias caused by measurement $\mathrm { e r r o r ^ { 1 3 } }$

$$
\boxed {b i a s (A) = - \beta_ {0} (\mu_ {1} - \mu_ {0}) \left(\frac {\sigma^ {2}}{\lambda_ {0} ^ {2} + \sigma^ {2}}\right).} \tag {10}
$$

The accuracy of the approximation is understood by considering

$$
A - A _ {X} ^ {a} = \beta_ {0} (\mu_ {1} - \mu_ {0}) \frac {\sigma^ {4}}{\lambda_ {0} ^ {2} (\lambda_ {0} ^ {2} + \sigma^ {2})}.
$$

# 7.3 Bias correction

Our bias correction procedure proposes subtracting from a consistent estimator of A a consistent estimator of $\sigma ^ { 2 } B ^ { * }$ , where $B ^ { * }$ is defined as follows

$$
B ^ {*} = \int \left[ E _ {Y _ {0} | D Z} ^ {\prime} (Y _ {0} | 0, z) \left(\frac {f _ {Z | D} ^ {\prime} (z | 0)}{f _ {Z | D} (z | 0)}\right) + E _ {Y _ {0} | D Z} ^ {\prime \prime} (Y _ {0} | 0, z) \right] f _ {Z | D} (z | 1) d z.
$$

The value of $B ^ { * }$ is now derived for this example. Since

$$
{E _ {Y _ {0} | D Z} ^ {\prime} (Y _ {0} | 0, z)} = {\frac {\beta_ {0} \lambda_ {0} ^ {2}}{\lambda_ {0} ^ {2} + \sigma^ {2}},}
$$

$$
E _ {Y _ {0} | D Z} ^ {\prime \prime} (Y _ {0} | 0, z) = 0,
$$

$$
{\left(\frac {f _ {Z | D} ^ {\prime} (z | 0)}{f _ {Z | D} (z | 0)}\right)} = {- \frac {1}{\lambda_ {0} ^ {2} + \sigma^ {2}} \left(z - \mu_ {0}\right),}
$$

it follows that

$$
B ^ {*} = - \frac {\beta_ {0} \lambda_ {0} ^ {2}}{(\lambda_ {0} ^ {2} + \sigma^ {2}) ^ {2}} (\mu_ {1} - \mu_ {0}).
$$

Using our proposed procedure produces a consistent estimator of

$$
A ^ {c o r} \equiv A - \sigma^ {2} B _ {Z} = \alpha_ {0} + \beta_ {0} \mu_ {1} - \beta_ {0} (\mu_ {1} - \mu_ {0}) \frac {\sigma^ {4}}{(\lambda_ {0} ^ {2} + \sigma^ {2}) ^ {2}}.
$$

So, after our correction procedure, the bias in (10) is replaced by a bias equal to

$$
\boxed {b i a s (A ^ {c o r}) = - \beta_ {0} (\mu_ {1} - \mu_ {0}) \left(\frac {\sigma^ {2}}{\lambda_ {0} ^ {2} + \sigma^ {2}}\right) ^ {2}.} \tag {11}
$$

# 8 Conclusions

This paper proposes a method for bias reduction in estimation of treatment effects based on ignorable assignment given a set of covariates, with one covariate subject to measurement error. Our procedure exploits nothing but the error contaminated covariate data.

In further work, we will look at exact calculations designed to investigate the performance of the proposed procedure. Moreover, we will apply the approach described here to real data.

# References

[1] Chesher, A. (1991), The Effect of Measurement Error, Biometrika, Vol. 78, No. 3, pp. 451-462   
[2] Chesher, A. (2000), Measurement Error Bias Reduction, unpublished manuscript, University College London   
[3] Chesher, A. and Schluter, C. (2002), Welfare Measurement and Measurement Error, Review of Economic Studies, Vol. , No. , pp. ??-??   
[4] Fr¨olich, M. (2003), Programme Evaluation and Treatment Choice, Lecture Notes in Economics and Mathematical Systems, Berlin: Spriger-Verlag   
[5] Hahn, (1998), On the Role of the Propensity Score in Efficient Semiparametric Estimation of Average Treatment Effects, Econometrica, Vol. 66, No. 2, pp. 315-331   
[6] Hausman, J.A. Newey, W.K. and Powell, J.L. (1998), Nonlinera Errors in Variables Estimation of Some Engel Curves, Journal of Econometrics, Vol. 66, No. 5, pp. 1017-1098   
[7] Heckman, J.J. Ichimura, H. Smith, J. and Todd, P. (1998), Characterizing Selection Bias Using Experimental Data, Econometrica, Vol. 65, No. , pp. 205-233   
[8] Heckman, J.J. Lalonde, R. and Smith, J. (1999), The Economics and Econometrics of Active Labor Market Programs, Handbook of Labor Economics, Volume 3, Ashenfelter, A. and Card, D. (eds.), Amsterdam: Elsevier Science   
[9] Hirano, K. Imbens, G. and Ridder, G. (2003), Efficient Estimation of Average Treatment Effects using the Estimated Propensity Score, Econometrica, Vol. 71, No. 4, pp. ???   
[10] Holland, P. (1986), Statistics and Causal Inference, Journal of the American Statistical Association, Vol. 81, No. 396, pp. 945-970   
[11] Horvitz, D.G. and Thompson, D.J. (1952), A Generalization of Sampling Without Replacement From a Finite Universe, Journal of the American Statistical Association, Vol. 47, No. 260, pp. 663-685   
[12] Imbens, G.W. (2004), Semiparametric Estimation of Average Treatment Effects under Exogeneity: a Review, Review of Economics and Statistics, forthcoming   
[13] Lechner, M. (2001), A note on the common support problem in applied evaluation studies, Discussion Paper 2001-01, Department of Economics, University of St. Gallen   
[14] Rosenbaum, P.R. (1987), Model-Based Direct Adjustment, Journal of the American Statistical Association, Vol. 82, No. 398, pp. 387-394   
[15] Rosenbaum, P.R. and Rubin, D.B. (1983), The central role of the propensity score in observational studies for causal effects, Biometrika, Vol. 70, No. 1, 41-55

[16] Rubin, D.B. (1977), Assignment to Treatment Group on the Basis of a Covariate, Journal of Educational Statistics, Vol. 2, 4-58   
[17] Wickens, M.R. (1972), A Note on the Use of Proxy Variables, Econometrica, Vol. 40, No. 4, pp. 759-761

# Appendix

# Proof of Proposition 2

Proof. Using the approximation to $E _ { Y _ { 0 } | D Z } ( Y _ { 0 } | 0 , z )$ and the approximation

$$
f _ {Z | D} (z | 1) \simeq f _ {X | D} (z | 1) + \frac {\sigma^ {2}}{2} f _ {X | D} ^ {\prime \prime} (z | 1)
$$

gives

$$
\begin{array}{l} { A } { \simeq } { \int \left( E _ { Y _ { 0 } | X } ( Y _ { 0 } | z ) + \sigma ^ { 2 } E _ { Y _ { 0 } | X } ^ { \prime } ( Y _ { 0 } | z ) \left( \frac { f _ { X | D } ^ { \prime } ( z | 0 ) } { f _ { X | D } ( z | 0 ) } \right) + \frac { \sigma ^ { 2 } } { 2 } E _ { Y _ { 0 } | X } ^ { \prime \prime } ( Y _ { 0 } | z ) \right) } \\ \times \left(f _ {X | D} (z | 1) + \frac {\sigma^ {2}}{2} f _ {X | D} ^ {\prime \prime} (z | 1)\right) d z \\ \end{array}
$$

and neglecting terms which are $o ( \sigma ^ { 2 } )$ there is the following expression for A:

$$
A \simeq E _ {Y _ {0} | D} [ Y _ {0} | 1 ] + \sigma^ {2} B
$$

where

$$
\begin{array}{l} B = \int E _ {Y _ {0} | D X} ^ {\prime} (Y _ {0} | 0, z) \left(\frac {f _ {X | D} ^ {\prime} (z | 0)}{f _ {X | D} (z | 0)}\right) f _ {X | D} (z | 1) d z \\ + \frac {1}{2} \int E _ {Y _ {0} | D X} ^ {\prime \prime} (Y _ {0} | 0, z) f _ {X | D} (z | 1) d z \\ + \frac {1}{2} \int E _ {Y _ {0} | D X} (Y _ {0} | 0, z) f _ {X | D} ^ {\prime \prime} (z | 1) d z. \\ \end{array}
$$

Consider the final term in this expression. On integrating by parts once we have

$$
\begin{array}{l} \int_ {- \infty} ^ {\infty} E _ {Y _ {0} | D X} (Y _ {0} | 0, z) f _ {X | D} ^ {\prime \prime} (z | 1) d z = \left[ E _ {Y _ {0} | D X} (Y _ {0} | 0, z) f _ {X | D} ^ {\prime} (z | 1) \right] _ {- \infty} ^ {\infty} \\ - \int_ {- \infty} ^ {\infty} E _ {Y _ {0} | D X} ^ {\prime} (Y _ {0} | 0, z) f _ {X | D} ^ {\prime} (z | 1) d z \\ \end{array}
$$

and if14 $\mathrm { i f ^ { 1 4 } }$

$$
\lim _ {z \to \pm \infty} E _ {Y _ {0} | D X} (Y _ {0} | 0, z) f _ {X | D} ^ {\prime} (z | 1) = 0
$$

there is

$$
\int_ {- \infty} ^ {\infty} E _ {Y _ {0} | D X} (Y _ {0} | 0, z) f _ {X | D} ^ {\prime \prime} (z | 1) d z = - \int_ {- \infty} ^ {\infty} E _ {Y _ {0} | D X} ^ {\prime} (Y _ {0} | 0, z) f _ {X | D} ^ {\prime} (z | 1) d z.
$$

Integrating by parts a second time gives

$$
\begin{array}{l} - \int_ {- \infty} ^ {\infty} E _ {Y _ {0} | D X} ^ {\prime} (Y _ {0} | 0, z) f _ {X | D} ^ {\prime} (z | 1) d z = - \left[ E _ {Y _ {0} | D X} ^ {\prime} (Y _ {0} | 0, z) f _ {X | D} (z | 1) \right] _ {- \infty} ^ {\infty} \\ + \int_ {- \infty} ^ {\infty} E _ {Y _ {0} | D X} ^ {\prime \prime} (Y _ {0} | 0, z) f _ {X | D} (z | 1) d z \\ \end{array}
$$

and if

$$
\lim _ {z \to \pm \infty} E _ {Y _ {0} | D X} ^ {\prime} (Y _ {0} | 0, z) f _ {X | D} (z | 1) = 0
$$

there is

$$
\int_ {- \infty} ^ {\infty} E _ {Y _ {0} | D X} (Y _ {0} | 0, z) f _ {X | D} ^ {\prime \prime} (z | 1) d z = \int_ {- \infty} ^ {\infty} E _ {Y _ {0} | D X} ^ {\prime \prime} (Y _ {0} | 0, z) f _ {X | D} (z | 1) d z
$$

and then

$$
\begin{array}{l} { B } { = } { \int E _ { Y _ { 0 } | D X } ^ { \prime } ( Y _ { 0 } | 0 , z ) \left( \frac { f _ { X | D } ^ { \prime } ( z | 0 ) } { f _ { X | D } ( z | 0 ) } \right) f _ { X | D } ( z | 1 ) d z } \\ + \int E _ {Y _ {0} | D X} ^ {\prime \prime} (Y _ {0} | 0, z) f _ {X | D} (z | 1) d z. \\ \end{array}
$$