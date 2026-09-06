# 古基因组 + 考古证据 + 数字人文 Agent：数据与工具链可行性调研

调研日期：2026-08-30  
运行环境：macOS，`uname -m` 实测为 `arm64`（Apple Silicon）  
项目状态：从零起步，Python 后端，约一周完成可演示版本，现场数据访问需完全离线

## 总体结论

从零完成一个可离线演示的 Agent 原型可行。最稳妥的数据制品是一个 SQLite 主库加一组按章节裁剪、预计算的数值文件：SQLite 保存个体、遗址、时段、论文、证据边、来源和不确定性；`.npy` 或压缩后的 PLINK/PGEN 子集保存 PCA 坐标、f3/allele-sharing 结果、距离矩阵及少量必要基因型。全量 AADR 可保留在构建机上，现场运行无需扫描 6.7 GiB 的全量基因型。

候选设想中“以 `Poseidon_ID`（即 AADR `Individual_ID`）作为唯一主键”与实测数据不符。Poseidon AADR Archive 的 `Poseidon_ID` 逐行对应 AADR `Genetic ID`，它标识一次可分析的遗传数据表示；AADR `Individual ID` 标识生物个体，同一人可有多个 `Genetic ID`。推荐同时保存三个键：`individual_id`（人级）、`genetic_representation_id`（数据表示级）和 `persistent_genetic_id`（跨 AADR 版本稳定的数据表示级），每个键附带 `namespace` 与 `release`。

一周内可以稳定覆盖：地点或个体检索、证据覆盖评估、地图与时间轴、论文来源回溯、已报告亲缘边、预计算的 PCA/f3/allele-sharing 结果、树状证据图和第三人称叙事。任意地点、任意传说、任意基因组都能实时完成完整科研分析，只能达到部分可行；公开考古资料缺乏统一数据库，历史地名许可有约束，低覆盖古 DNA 的统计分析也不适合在路演现场临时运行。

## 1. AADR（Allen Ancient DNA Resource）

### 1.1 最新版本、下载、访问与大小

截至 2026-08-30，官方 Harvard Dataverse 最新发布为 **AADR v66.p1 / Dataverse V14.0，发布日期 2026-06-08**。数据集采用 CC0 1.0，文件状态为 Public，无需注册或申请。官方页面同时记录了 v66.0 和 v62.0 被替换的原因：旧包误纳入 161 名应由 EGA Data Access Committee 管理的现代巴布亚个体，现行版本应固定到 `v66.p1`。[AADR Dataverse](https://doi.org/10.7910/DVN/FFIDCW)；[AADR 数据论文](https://doi.org/10.1038/s41597-024-03031-7)。

1240K 主文件的确切下载地址与 Dataverse 元数据实测大小如下。四个核心文件合计 **7,209,417,659 bytes，即 7.209 GB / 6.714 GiB**。

| 文件 | 确切下载 URL | 大小 |
|---|---|---:|
| `v66.p1_1240K.aadr.patch.PUB.geno` | https://dataverse.harvard.edu/api/access/datafile/13994829 | 7,117,276,654 bytes |
| `v66.p1_1240K.aadr.patch.PUB.ind` | https://dataverse.harvard.edu/api/access/datafile/13994513 | 1,017,460 bytes |
| `v66.p1_1240K.aadr.patch.PUB.snp` | https://dataverse.harvard.edu/api/access/datafile/13994514 | 77,679,819 bytes |
| `v66.p1_1240K.aadr.PUB.anno` | https://dataverse.harvard.edu/api/access/datafile/13994515 | 13,443,726 bytes |
| v66.p1 README | https://dataverse.harvard.edu/api/access/datafile/13994530 | 约 265 KB |

Dataverse 还提供 2M、2M compatibility、HO 和 compatibility_HO 面板。官方 README 列出的 `.geno` 近似大小分别为 12 GB、6.8 GB、3.8 GB 和 1.8 GB。对一周原型，1240K 足以支持成熟工具链和现有论文结果复现；全量 2M 面板增加下载与转换成本。[AADR Dataverse](https://doi.org/10.7910/DVN/FFIDCW)。

### 1.2 基因型格式

v66.p1 由 `.geno/.snp/.ind` 三个 EIGENSTRAT 体系文件和 `.anno` 注释表组成，但 `.geno` 的物理编码已更新为 **`transpose_packed`，README 中简称 `tgeno`**。它既非逐字符文本 EIGENSTRAT，也非旧版 `packedancestrymap`。新版 `convertf` 可以把它转换为文本 `eigenstrat` 或旧的 packed 格式；旧版 EIGENSOFT/ADMIXTOOLS 无法读取。`.snp` 使用 hg19 坐标；1240K 面板含 1,233,013 个 SNP。`.anno` 是 UTF-8、tab-separated text。[v66.p1 README](https://dataverse.harvard.edu/api/access/datafile/13994530)；[EIGENSOFT/convertf](https://github.com/DReichLab/EIG)。

### 1.3 `.anno` 的 49 个确切字段

以下字段直接读取 v66.p1 `.anno` 首行所得，共 49 列：

1. `Genetic ID (suffices: ".DG" is a high coverage shotgun genome with diploid genotype calls; ".SG" is a high coverage shotgun genome with diploid genotype calls; ".AG,  .TW, .BY, .AA, .EC, .WGC"  are Agilent 1240K or Twist Ancient DNA or "Big Yoruba" or "Archaic Admixture" or "Exome" or "Whole-Genome Capture" data respectively; each analyzed position is represented by a randomly chosen sequence allowing for combinations when merged (separable by readgroups if possible).  ".HO" is Affymetrix Human Origins genotype data and "REF" is reference haploid data.`
2. `Persistent Genetic ID`
3. `Individual ID`
4. `Skeletal code`
5. `Skeletal element`
6. `First publication: Abbreviation for earliest paper that reported data from this individual (this is not always the same as the data being analyzed, which may be from a different or improved dataset)`
7. `Publication abbreviation`
8. `doi for publication of this representation of the data`
9. `Link to the most permanent repository hosting these data`
10. `Method for Determining Date; unless otherwise specified, calibrations use 95.4% intervals from OxCal v4.4.2 Bronk Ramsey (2009); r5; Atmospheric data from Reimer et al (2020)`
11. `Date mean in BP in years before 1950 CE [OxCal mu for a direct radiocarbon date, and average of range for a contextual date]`
12. `Date standard deviation in BP [OxCal sigma for a direct radiocarbon date, and standard deviation of the uniform distribution between the two bounds for a contextual date]`
13. `Full Date One of two formats. (Format 1) 95.4% CI calibrated radiocarbon age (Conventional Radiocarbon Age BP, Lab number) e.g. 2624-2350 calBCE (3990+-40 BP, Ua-35016). (Format 2) Archaeological context range, e.g. 2500-1700 BCE`
14. `Age at death, Morphological sex from physical anthropology`
15. `Group ID`
16. `Locality`
17. `Political Entity`
18. `Latitude`
19. `Longitude`
20. `Pulldown Strategy`
21. `Suffices (indicating data types used for sources which can be a subset of that in bam)`
22. `Data type`
23. `No. Libraries`
24. `Mean coverage on 1.15M autosomal targets for full bam (if no off-target entry not up-to-date)`
25. `Mean coverage on non-targeted autosomal SNPs for full bam - not yet computed if "".."" and bam restricted to on-target SNPs if ""0""`
26. `SNPs hit on autosomal targets (Computed using easystats on enhance 2M capture subset)`
27. `SNPs hit on autosomal targets (Computed using easystats on 1240k snpset)`
28. `SNPs hit on autosomal targets (Computed using easystats on HO snpset)`
29. `SNPs hit on autosomal targets (Computed using easystats on Compatibility snpset)`
30. `SNPs hit on autosomal targets (Computed using easystats on Compatibility_HO snpset)`
31. `Molecular Sex`
32. `Family relations`
33. `Sum total of ROH segments >20cM`
34. `Sum total of ROH segments >20cM`（源文件第 33、34 列标题重复）
35. `Y haplogroup in terminal mutation notation automatically called based on Y-full 12.03 with the software described in Lazaridis et al. Science 2022`
36. `Y haplogroup  in ISOGG notation automatically called based on Yfull 12.03 with the software described in Lazaridis et al. Science 2022`
37. `Y haplogroup manually called if different from automatic`
38. `mtDNA coverage (merged data)`
39. `mtDNA haplogroup if >2x or published`
40. `mtDNA match to consensus if >10x (merged data) [estimates are typically off by (uncorrected + power(10,-0.271*LOG(mt-coverage)-1.120)]`
41. `Damage rate in first nucleotide on sequences overlapping 1240k targets (merged data)`
42. `Sex ratio [Y/(Y+X) counts] (merged data)`
43. `ANGSD MOM 95% CI truncated at 0 (only if male and >=200 SNPs) [estimates are typically 0.005 too high]`
44. `hapConX 95% CI truncated at 0 (only if male and >=2000 SNPs covered on X chromosome) [estimates are typically 0.005 too high]`
45. `Library type (minus=no.damage.correction, half=damage.retained.at.last.position, plus=damage.fully.corrected, ds=double.stranded.library.preparation, ss=single.stranded.library.preparation)`
46. `Libraries`
47. `endogenous by library (computed on shotgun data)`
48. `ASSESSMENT`
49. `ASSESSMENT WARNINGS: X contamination interval is listed if lower bound is >=0.005 for either ANGSD or hapConX, "QUESTIONABLE" if lower bound is 0.015-0.035 for hapConX (or ANGSD if no hapConX computation), "CRITICAL" or "FAIL" if lower bound is >0.03  for hapConX (or ANGSD if no hapConX computation) |mtcontam confidence interval is listed if coverage >10 and upper bound is <0.98, "QUESTIONABLE" if upper bound is 0.9-0.95; "CRITICAL" if upper bound is <0.9, QUESTIONABLE status gets overriden by ANGSD or hapConX if upper bound of contamination estimate is <0.01 | damage for ds.half is "CRITICAL/FAIL" if <0.01, and recorded but passed if 0.01-0.03; libraries with untreated last base are "CRITICAL" or "FAIL" if <0.01, "QUESTIONABLE" if 0.01-0.03, and recorded but passed if 0.03-0.1 | sex.ratio is QUESTIONABLE if [0.03,0.1) or (0.30,0.32]; CRITICAL/FAIL if [0.1,0.3] | f4(All,Damage;CEU,CHB) for non-damage-restricted samples is "CRITICAL/FAIL" if |Z|>=3.5, QUESTIONABLE if 3.5>Z>=3.0, listed if Z>=2.0`

字段来源：[v66.p1 `.anno`](https://dataverse.harvard.edu/api/access/datafile/13994515)。

### 1.4 中国境内样本量、时段和字段覆盖率

统计方法：下载 v66.p1 1240K `.anno`，筛选 `Political Entity == China`；古代个体按 `Date mean BP > 0`；用 `Individual ID` 折叠多个数据表示。由此得到 1,479 条中国相关数据表示，其中 **918 个古代 `Individual ID`，对应 957 条遗传数据表示**。这些数字描述 AADR 收录的已发表基因组证据覆盖，不代表历史人口密度。

| 项目 | 918 个中国古代个体中的覆盖 | 解释 |
|---|---:|---|
| 经纬度均存在 | 911 / 918，99.2% | 坐标精度需回看论文，数据库没有统一误差半径 |
| 测年均值 | 918 / 918，100% | 日期可能来自直接 C14，也可能来自考古语境；应同时保留 method、SD 和 Full Date |
| 遗传性别字段 | 918 / 918，100% | 480 M、339 F、99 U；可解析为 M/F 的覆盖为 89.2% |
| Y 单倍群 | 410 / 480 遗传男性，85.4% | 合并自动 terminal、ISOGG 和 manual 三列统计 |
| mtDNA 单倍群 | 424 / 918，46.2% | 排除 `..` 与 `n/a (<2x)` |
| 论文缩写与 DOI | 918 / 918，100% | 仍需引用构成数据的原始论文 |
| Group ID | 918 / 918，100% | Group label 是分析分组标签，不能直接视为民族或谱系 |
| Family relations | 93 / 918，10.1% | 有值并不等于已完成可展示家谱，需要解析关系对并复核原论文 |

中国古代个体的 `Date mean BP` 范围为 127–39,565 BP。按个体计数的时间分箱为：0–1,000 BP 64；1,000–3,000 BP 434；3,000–5,000 BP 265；5,000–10,000 BP 141；10,000–20,000 BP 12；20,000–50,000 BP 2。AADR 的深时段记录明显稀疏，Agent 应把这种结果表述为“该数据库在此时段的已发表证据较少”。来源：[v66.p1 `.anno`](https://dataverse.harvard.edu/api/access/datafile/13994515)，上述比例为本次逐行复算结果。

### 1.5 许可与引用

Dataverse 对数据集标注 **CC0 1.0**，公开 demo 可以使用。AADR 团队要求引用 Dataverse DOI、具体 release、AADR 数据论文，并引用实际进入叙事或分析的每篇原始论文。CC0 覆盖 AADR 数据文件；原论文正文、图片和补充材料仍各自受其出版许可约束。[AADR Dataverse](https://doi.org/10.7910/DVN/FFIDCW)；[Scientific Data 论文](https://doi.org/10.1038/s41597-024-03031-7)。

### 1.6 已知坑与数据组织建议

v66.p1 有 23,089 行、21,433 个唯一 `Individual ID`；1,262 个 `Individual ID` 有多个数据表示，额外表示共 1,656 行。一个人在新测序、不同 capture panel 或重新处理后会出现多个 `Genetic ID`。选择策略可以优先通过 QC 的表示，再按目标面板 SNP 覆盖数择优，原始候选仍要保留以便审计。

AADR 的 `Genetic ID` 会跨 release 改名，`Persistent Genetic ID` 用于跟踪底层变异数据未改变的表示；`Individual ID` 用于合并同一生物个体。数据库结构应把三个 ID 分列，任何外部边都记录原始 source ID。AADR README 还明确说明其团队会从 BAM/FASTQ 重新处理并统一 pseudo-haploid calling，所以 AADR genotype 可能和原论文分析文件不完全一致。[v66.p1 README](https://dataverse.harvard.edu/api/access/datafile/13994530)。

Group ID、地理接近、PCA 接近和 qpAdm 模型都缺少个体家谱语义。Agent 输出中应保留关系类型：`reported_kinship`、`genetic_affinity`、`same_site`、`contemporaneous`、`modelled_ancestry`，并分别携带来源和证据等级。

**结论：可行。** AADR 足以作为基因组骨架与主要样本元数据源，许可证和公开访问满足 demo。  
**替代方案：** 官方下载不畅时，使用 Poseidon AADR Archive 的 v66.p1 包；保留 AADR DOI、release 和原论文引用，镜像仅承担传输与格式转换。

## 2. Poseidon 框架

### 2.1 `.janno` schema 与亲缘字段

Poseidon Standard v3.0.0 的 `.janno` 是 **UTF-8 TSV 纯文本**，`POSEIDON.yml` 才是 YAML。标准定义 52 个字段：

`Poseidon_ID`, `Genetic_Sex`, `Group_Name`, `Individual_ID`, `Species`, `Alternative_IDs`, `Alternative_IDs_Context`, `Relation_To`, `Relation_Degree`, `Relation_Type`, `Collection_ID`, `Custodian_Institution`, `Cultural_Era`, `Cultural_Era_URL`, `Archaeological_Culture`, `Archaeological_Culture_URL`, `Country`, `Country_ISO`, `Location`, `Site`, `Latitude`, `Longitude`, `Date_Type`, `Date_C14_Labnr`, `Date_C14_Uncal_BP`, `Date_C14_Uncal_BP_Err`, `Date_BC_AD_Start`, `Date_BC_AD_Median`, `Date_BC_AD_Stop`, `Chromosomal_Anomalies`, `MT_Haplogroup`, `Y_Haplogroup`, `Source_Material`, `Nr_Libraries`, `Library_Names`, `Capture_Type`, `UDG`, `Library_Built`, `Genotype_Ploidy`, `Data_Preparation_Pipeline_URL`, `Endogenous`, `Nr_SNPs`, `Coverage_on_Target_SNPs`, `Damage`, `Contamination`, `Contamination_Err`, `Contamination_Meas`, `Genetic_Source_Accession_IDs`, `Primary_Contact`, `Publication`, `Note`, `Keywords`。

其中 schema 强制的核心列只有 `Poseidon_ID`、`Genetic_Sex` 和 `Group_Name`。`Relation_To` 指向 `Individual_ID`；`Relation_Degree` 的受控值包括 `identical`、`first`、`second`、`thirdToFifth`、`sixthToTenth`、`unrelated`、`other`；`Relation_Type` 为自由文本。[Poseidon schema](https://github.com/poseidon-framework/poseidon-schema)；[字段定义 TSV](https://raw.githubusercontent.com/poseidon-framework/poseidon-schema/master/janno_columns.tsv)；[Poseidon Standard](https://github.com/poseidon-framework/poseidon-schema/blob/master/poseidon_package_specification.pdf)。

### 2.2 AADR Poseidon 包与真实填充率

Poseidon AADR Archive 已有 `AADR_v66_p1_1240K` 包：[Archive repository](https://github.com/poseidon-framework/aadr-archive)；[在线 explorer](https://server.poseidon-adna.org/explorer/aadr-archive)；[package manifest](https://raw.githubusercontent.com/poseidon-framework/aadr-archive/main/AADR_v66_p1_1240K/POSEIDON.yml)；[完整 `.janno`](https://raw.githubusercontent.com/poseidon-framework/aadr-archive/main/AADR_v66_p1_1240K/AADR_v66_p1_1240K.janno)。

本次下载并检查该 `.janno`：23,089 行、63 列，其中 52 列来自标准 schema，其余是 `AADR_*` 扩展列。标准亲缘三列 `Relation_To`、`Relation_Degree`、`Relation_Type` 的非空率均为 **0%**。自定义列 `AADR_Family_Relations` 有 3,747 行提供实际关系文本，另有 201 行写作 `n/a`；实际可用填充率为 16.2%。中国古代数据表示中约 10.6% 有该自定义字段。Poseidon schema 能表达亲缘关系，现成 AADR 转换包没有把 AADR 的自由文本关系转换到三列标准关系字段。

该包用 gzip 压缩的 PLINK BED/BIM/FAM。文件元数据总计约 **4.600 GB / 4.284 GiB**：BED 4,568,711,811 bytes；BIM 13,895,442；FAM 892,464；JANNO 16,480,151；BIB 383,521。它比官方 1240K `tgeno` 更容易被 PLINK 和 READ 消费。[Poseidon AADR Archive](https://github.com/poseidon-framework/aadr-archive)。

### 2.3 ID 实测

对 23,089 行逐行比对得到：

- `Poseidon_ID == AADR Genetic ID`：23,089 / 23,089。
- `Poseidon_ID == AADR Individual ID`：0 / 23,089。
- Poseidon `Individual_ID == AADR Individual ID`：23,057 / 23,089；32 行经过转换或清洗，需要保留 `AADR_Individual_ID` 原值。

运行库可采用复合唯一约束 `(source_namespace, source_release, genetic_representation_id)`；人级图节点使用内部 UUID，并维护 AADR `Individual ID`、Poseidon `Individual_ID` 和其他论文 ID 的映射表。这样可以让同一个人挂接多个数据表示，也能处理跨数据库重名。

### 2.4 trident 在 Apple Silicon 上的可安装性

trident 最新 release 为 v2.1.0.0，官方提供 macOS ARM64 单文件二进制，约 97.6 MB，可直接放到项目的 `tools/bin/trident`：

https://github.com/poseidon-framework/poseidon-hs/releases/download/v2.1.0.0/trident-macOS-ARM64

发布页确认 v2.1.0.0 针对 AADR v66 的大于 4 GB 包重写了流式传输；`fetch` 解压大包时仍会出现明显内存峰值。[trident v2.1.0.0](https://github.com/poseidon-framework/poseidon-hs/releases/tag/v2.1.0.0)。

trident 对下载、validate、forge 和格式转换很有用。只读取 `.janno` 和 `POSEIDON.yml` 时，Python 标准库 `csv` 加 PyYAML（仅在确实读取 YAML 时）即可完成；运行时无需把 trident 作为依赖。最小原型甚至可以只解析 `.janno`，把 package manifest 的固定信息在构建阶段写入 SQLite。

**结论：部分可行。** Poseidon 提供成熟 schema、AADR 镜像和原生 ARM64 工具；现成包的标准亲缘列为空，且 `Poseidon_ID` 处在遗传数据表示层。  
**替代方案：** 元数据直接解析 `.janno`；亲缘关系从 AADR 自定义列和论文补充表重新结构化，保留原始文本、来源和人工确认状态。

## 3. 生信工具在本机 macOS ARM64 上的可安装性

### 3.1 安装结论与路径

| 工具 | Apple Silicon 可用性 | 推荐安装路径 | 事实来源 |
|---|---|---|---|
| PLINK 1.9 | 可用；官网 stable beta 7.11 的 macOS 64-bit 包未单列 ARM，Bioconda 有原生 `osx-arm64` 1.90b7.7 | Conda 环境 `./envs/adna/bin/plink` | [PLINK 1.9](https://www.cog-genomics.org/plink/)；[Bioconda ARM64 文件](https://anaconda.org/bioconda/plink/files) |
| PLINK 2.0 | 可用；官网 Alpha 7.4（2026-08-18）有 `macOS M1` 二进制 | 官方 ZIP 解压到 `./tools/bin/plink2` | [PLINK 2.0](https://www.cog-genomics.org/plink/2.0/)；[M1 ZIP](https://s3.amazonaws.com/plink2-assets/alpha7/plink2_mac_arm64_20260818.zip) |
| EIGENSOFT / `convertf`, `smartpca` | 可用；源码主分支标注 9.0.0 为 Linux only，Bioconda 提供原生 `osx-arm64` 8.0.0 | Conda 环境 `./envs/adna/bin/convertf`、`smartpca` | [EIGENSOFT](https://github.com/DReichLab/EIG)；[Bioconda ARM64 文件](https://anaconda.org/channels/bioconda/packages/eigensoft/files) |
| ADMIXTOOLS / `qp3Pop` | 可用；官方 tagged release 与 Bioconda 均为 8.0.2，Bioconda 有原生 `osx-arm64` | Conda 环境 `./envs/adna/bin/qp3Pop` 等 | [ADMIXTOOLS releases](https://github.com/DReichLab/AdmixTools/releases)；[Bioconda](https://anaconda.org/bioconda/admixtools) |
| READv2 | 可用；Python ≥3.7，Bioconda `kinship-read` 2.1.1 为 noarch | Conda 环境中执行 `READ2.py`；依赖 PLINK BED/BIM/FAM | [READv2](https://github.com/GuntherLab/READv2)；[Bioconda](https://anaconda.org/bioconda/kinship-read) |
| HaploGrep 3 | 可用；跨平台 Java 11+，最新 release v3.3.2 | JAR 与 tree/config 一起放 `./tools/haplogrep3/`，Java 使用 ARM64 JDK | [HaploGrep 3](https://github.com/genepi/haplogrep3)；[releases](https://github.com/genepi/haplogrep3/releases) |

推荐使用项目内 Conda prefix，避免改变系统 Python。可执行安装命令如下；本次调研确认包和平台存在，未在当前目录实际创建环境：

```bash
conda create -p ./envs/adna -c conda-forge -c bioconda \
  python=3.11 numpy pandas scipy \
  plink=1.90b7.7 eigensoft=8.0.0 admixtools=8.0.2 kinship-read=2.1.1
```

PLINK 2.0 使用官网 M1 build。HaploGrep 3 使用官方 release JAR；Bioconda 中的 `haplogrep` 属于旧版 2.x，不适合作为 HaploGrep 3 的等价安装来源。ADMIXTOOLS 和 EIGENSOFT 均可源码编译，但会涉及 GSL、OpenBLAS/LAPACK、gfortran 与 Apple Silicon 路径配置，一周原型没有使用源码编译的必要。[EIGENSOFT build notes](https://github.com/DReichLab/EIG)；[ADMIXTOOLS](https://github.com/DReichLab/AdmixTools)。

READv2 接受 PLINK BED/BIM/FAM，假设 pseudohaploid 数据。官方文档建议对非 UDG 或损伤水平不一致的样本限制到 transversions；默认 normalization 假设同组多数配对无亲缘，样本很少或混合来源时应提供外部 normalization value。[READv2 README](https://github.com/GuntherLab/READv2)。HaploGrep 处理 mtDNA VCF/FASTA 等输入，不能从 AADR 1240K 核基因组矩阵直接恢复完整线粒体单倍群；AADR 已报告的 mtDNA 字段更适合首版。

### 3.2 “现代人群做底、古样本投影”的 PCA 能否用 Python 完成

可以完成。推荐构建阶段运行，现场加载坐标。实现要点如下：

1. 统一 hg19 build、SNP ID、REF/ALT 与 strand；A/T、C/G 位点在缺少可靠频率或参考信息时剔除。
2. 在现代 reference samples 上完成 missingness/MAF 过滤和 LD pruning。
3. 只用现代 reference 估计每个 SNP 的等位频率 `p`，按 Patterson scaling 将二倍体计数标准化为 `(g - 2p) / sqrt(2p(1-p))`。
4. 在现代 reference 矩阵上执行 SVD/PCA，固定 mean、scale 和 loadings。
5. 古样本使用其实际观测位点投影。高缺失率样本可对每个个体在观测 SNP 上解 least-squares；直接把缺失值填为总体均值会把低覆盖古样本向原点收缩。
6. 用 EIGENSOFT `smartpca` 的 `lsqproject: YES` 输出做小规模数值对照；古样本投影常见的 axis shrink/伸展也要观察 `shrinkmode` 或等价校正。[EIGENSOFT POPGEN README](https://github.com/DReichLab/EIG/blob/master/POPGEN/README)；[PLINK 2 PCA/投影说明](https://www.cog-genomics.org/plink/2.0/strat)；[PLINK 2 scoring](https://www.cog-genomics.org/plink/2.0/score)。

纯 NumPy 足以实现上述流程，`scikit-allel` 或 `sgkit` 可以提供便利的数据结构，但会增加依赖和格式转换。对一周原型，PLINK 2 / EIGENSOFT 负责转换与基准结果，NumPy 负责读取预先裁剪的矩阵和生成展示制品，更容易审计。

### 3.3 outgroup-f3 与 allele-sharing 距离能否用 Python 完成

outgroup-f3 的点估计可用 NumPy 实现。对每个 SNP 计算 `(p_X - p_O) * (p_Y - p_O)`，再在有效 SNP 上求均值；等位基因方向必须一致，群体频率要按实际非缺失染色体数估计。科研级输出还需要按遗传图谱做 block jackknife，常用约 5 cM block，输出标准误与 Z 值。pseudohaploid 个体、极低覆盖、群体大小不均和面板差异都会改变方差与可比性。[ADMIXTOOLS `qp3Pop` 说明](https://github.com/DReichLab/AdmixTools/blob/master/README.3PopTest)；[ADMIXTOOLS 2 f3 文档](https://uqrmaie1.github.io/admixtools/reference/f3blockdat_from_geno.html)；[block jackknife](https://uqrmaie1.github.io/admixtools/articles/resampling.html)。

个体间 allele-sharing/Hamming distance 更直接：只在两者共同观测 SNP 上累计匹配或不匹配，并输出共同位点数、transversion-only 标记和 bootstrap/jackknife 区间。不同 pair 的有效位点集合不同，未经校正的距离不能排序成家谱关系。

工程判断为：Python 能生成 demo 所需的点估计、矩阵和可视化结果；与 `smartpca`、`qp3Pop` 在小型固定数据集上做数值回归后，可以脱离这些命令行工具运行现场版本。任何带标准误、Z 值或关系分类的结果仍应保留验证记录。

**结论：可行。** 六类工具均有 Apple Silicon 可落地的安装路线，PCA、f3 点估计和 allele-sharing 可以在 Python 构建管线中完成。  
**替代方案：** EIGENSOFT/ADMIXTOOLS 安装失败时，用 PLINK 2 做格式与 PCA 基准，用 NumPy 预计算展示结果；亲缘关系首版直接采用论文报告值，不在现场运行 READ。

## 4. CHGIS（中国历史地理信息系统）

CHGIS V6 发布于 2016 年，官方入口为 https://chgis.fas.harvard.edu/data/chgis/v6/ ，Harvard Dataverse 集合为 https://dataverse.harvard.edu/dataverse/chgis_v6 。项目目标时段为 **221 BCE–1911 CE**；Time Series 主要覆盖传统核心 22 省，内蒙古、青海、新疆、西藏不在完整 Time Series 范围内，但可在部分 time-slice 中出现。现有完整或较完整 time-slice 包括 1820、1911，另有 1990 census 数据。[CHGIS V6](https://chgis.fas.harvard.edu/data/chgis/v6/)；[CHGIS intro](https://chgis.fas.harvard.edu/pages/intro/)。

数据通过 Harvard Dataverse 提供 zipped Esri Shapefile，常见版本有 UTF-8/GBK 编码以及 WGS84/Xian80 坐标系。官方 how-to 将数据分为 Time Series、Time Slice 和 basemap，并说明记录含异步生效的 begin/end dates。[CHGIS how-to](https://chgis.fas.harvard.edu/pages/howto/)。可直接参考的包包括：[Prefecture polygons](https://doi.org/10.7910/DVN/I0Q7SM)、[Prefecture points](https://doi.org/10.7910/DVN/WW1PD6)、[County points](https://doi.org/10.7910/DVN/Q9VOF5)、[1911 UTF-8](https://doi.org/10.7910/DVN/HHVVHX)、[1820 UTF-8](https://doi.org/10.7910/DVN/ST5KKM)。

本地化可行。首版只导入 point layers，把 CHGIS unique ID、名称及异名、feature type、begin/end year、经纬度、父级关系和来源写入 SQLite；查询键使用 `name/alias + year + containing region`。多边形只用于确实需要历代疆域变化的章节，避免一开始承担投影、拓扑和大体积底图工作。

许可条款构成实际限制。CHGIS V6 官方页写明：免费用于 academic research，禁止 commercial use、resale 和 redistribution，并要求引用 CHGIS Version 6。部分 Dataverse 子数据页可能显示 CC0，项目官方 V6 页给出的专门许可更具体。面向投资人与公众的 hackathon 展示是否属于 non-commercial academic use 缺乏明确答案；公开发布应用时不能把完整 CHGIS layer 随包再分发，商业化路线需要联系权利方。[CHGIS V6 license](https://chgis.fas.harvard.edu/data/chgis/v6/)。

CHGIS 的 Temporal Gazetteer/API 可作构建期查询来源，现场仍需预取。官方入口：[CHGIS search](https://chgis.fas.harvard.edu/search/)；[Temporal Gazetteer](https://maps.cga.harvard.edu/tgaz/)。

**结论：部分可行。** 数据结构和本地查询很适合历史地名沿革，时空覆盖和商业/再分发许可限制了它作为全域唯一底库的用途。  
**替代方案：** 首版只导入人工确认的地名子集及其 CHGIS source ID；许可不清时，用 Wikidata CC0、国家文物信息页面和原始论文构建可引用的最小地名表。

## 5. Wikidata 作为考古遗址与地名兜底源

官方 SPARQL endpoint 为 https://query.wikidata.org/sparql 。Wikidata Query Service 对单次查询设置约 60 秒超时，并按 User-Agent/IP 限制处理时间、错误查询和并发；429 与查询超时属于正常的服务保护行为。官方文档还说明查询结果可能相对 Wikidata 主库有同步延迟。[Wikidata data access](https://www.wikidata.org/wiki/Help:Data_access)；[WDQS implementation limits](https://www.mediawiki.org/wiki/Wikidata_Query_Service/Implementation)。本次调研向 endpoint 提交限定五个 QID 的小查询，两次未获得响应，而单个 item 页面均可访问。现场依赖 SPARQL 不可取。

### 5.1 五个中国遗址抽查

| 遗址 | QID | 坐标 | 可直接用于考古叙事的数值年代 |
|---|---|---|---|
| 半坡 | [Q806929](https://www.wikidata.org/wiki/Q806929) | 有，34°16′28″N, 109°2′51″E | 无；1961 是文保 designation 日期 |
| 二里头 | [Q2692927](https://www.wikidata.org/wiki/Q2692927) | 有，34°41′33″N, 112°41′24″E | 无；仅有 Erlitou/Longshan culture 标签 |
| 三星堆 | [Q929072](https://www.wikidata.org/wiki/Q929072) | 有，30°59′37.388″N, 104°11′59.374″E | 无；`Bronze Age` 是宽泛时段标签，1988 是文保日期 |
| 良渚遗址 | [Q15904183](https://www.wikidata.org/wiki/Q15904183) | 有，30°23′48″N, 119°59′7″E | 无；1996/2013/2019 是文保与 UNESCO 日期 |
| 周口店 | [Q499552](https://www.wikidata.org/wiki/Q499552) | 有，39°41′20.26″N, 115°55′29.39″E | 无；仅有 Paleolithic 等宽泛标签 |

抽查结果为坐标 5/5，可靠的考古占用起止年 0/5。许多 instance、culture、coordinate statement 的 reference 数为 0 或只写“imported from Wikipedia”。`P580/start time` 经常挂在 heritage designation 上，不能当作遗址年代。Wikidata 适合补齐 QID、名称、多语言别名、坐标、图片链接和外部标识符，考古年代与文化判断需要回到论文、发掘报告或权威遗产页面。

### 5.2 本地化策略

在构建期按选定遗址 QID 调用 `Special:EntityData/QID.json` 或 `wbgetentities`，只保存需要的实体子集。SQLite 中分开记录：`site_chronology`、`heritage_designation_date`、`discovery_date` 和 `wikidata_claim`，禁止把不同日期语义合并成一个 `start_date`。每条 claim 保存 property、rank、qualifier、reference URL、retrieved date 和人工审核状态。Wikidata structured data 为 CC0，适合随 demo 本地分发。[Wikidata item page license](https://www.wikidata.org/wiki/Q806929)。

**结论：部分可行。** Wikidata 对名称、别名、坐标、QID 和外部链接有用，考古年代与证据出处质量不足，SPARQL 也不适合现场调用。  
**替代方案：** 构建期预取少量 QID，并用论文或官方遗址来源覆盖 chronology；没有可信年代时在界面保留未知，不从 heritage date 推断。

## 6. 古 DNA 亲缘关系的公开来源

### 6.1 已发表补充材料实例

1. **Shimao，Nature 2025**：研究发布 144 个用于总体分析的古基因组，并对另 25 个有一、二级亲缘的个体进行亲缘分析；Supplementary Table 3 记录近亲结果，Supplementary Table 12 记录 IBD 连接。论文页面可直接下载 Supplementary Tables 1–14 的 XLSX。[论文与补充材料](https://www.nature.com/articles/s41586-025-09799-x)。
2. **Avar communities，Nature 2024**：424 人，约 300 人进入大型 pedigrees，跨度可达 9 代；论文页面提供补充表并说明四个墓地的亲缘、IBD 和考古上下文。[论文](https://www.nature.com/articles/s41586-024-07312-4)。
3. **Gurgy，Nature 2023**：94 个有基因组结果的个体；pedigree A 含 64 人、7 代，pedigree B 含 12 人、5 代；Supplementary Tables 8–10 含 READ/lcMLkin 和 pedigree 相关结果。[论文](https://www.nature.com/articles/s41586-023-06350-8)。

另一个中国实例是北长江新石器墓葬 M13：论文报告 3 对一级、5 对二级、5 对三级关系，数据位于 Supplementary Data 5。[Nature Communications 2025](https://www.nature.com/articles/s41467-025-63743-1)。这些实例说明亲缘关系表通常能随论文补充材料公开取得，但表头、ID、relation wording 和置信度格式缺少统一标准。

### 6.2 不运行 READ 能支撑多少“家族”节点

AADR v66.p1 的 `Family relations` 有 3,747 条非空且非 `n/a` 的数据表示。解析关系字符串并按 `Individual ID` 去重后，本次统计得到约 8,303 个全局唯一报告关系对、3,492 个涉及关系的个体和 919 个 connected components。部分 component 因远亲网络、跨墓地连接、重复方向和自由文本解析而很大，它们只能作为候选集合。

中国境内且双方都能映射到中国古代个体的结果更适合估算首版工作量：约 **84 个唯一关系对、93 个个体、34 个 connected components**；其中 23 个二人组件、5 个三人组件，另有少量 4–9 人组件。把关系限制到字段中标为 2 度以内后，约 66 对、76 人、28 个组件。来源为 [AADR v66.p1 `.anno`](https://dataverse.harvard.edu/api/access/datafile/13994515)，数字由本次对 `Family relations` 自由文本的程序化解析得到，需在进入正式叙事前逐对回查原论文。

因此，不运行 READ 也足以支撑中国范围“几十个候选家族组件”和全球“数百个候选组件”。一周 demo 可以挑选一个补充表结构清晰、墓葬上下文充分的 pedigree；其关系边标记为 `reported_by_paper`，同时保存 method（READ/lcMLkin/KIN/IBD）、degree、confidence 和 table locator。生物亲缘与社会亲属是两个字段，叙事不得由前者自动推出继承、婚姻、族属或社会身份。

**结论：可行。** 论文补充材料和 AADR 汇总字段已提供足量亲缘边，首版无需重新运行 READ。  
**替代方案：** 补充表难以机器解析时，人工录入一个经过论文核对的 pedigree 子图；后续再增加 READ/lcMLkin/IBD 计算管线。

## 7. 竞品核实：DORA 与 Human AGEs

### 7.1 DORA

真实网址为 https://dora.modelrxiv.org/ ，本次调研已打开其当前页面，界面包含 polygon region、dataset、analysis、variants 和 timeline。帮助页为 https://dora.modelrxiv.org/help.html ，源码为 https://github.com/carrowkeel/dora ，论文 DOI 为 https://doi.org/10.1093/nar/gkae373 。

DORA 将 AADR 元数据/基因型、环境层和用户上传数据放在交互地图与时间轴上，支持 region selection、PCA、FST、allele frequencies、polygenic scores 等分析。它具有动态图层和分析功能，功能范围已经超过静态地图；主要交互单位仍是数据集、区域和统计分析，没有面向公众问题的 Agent 调查流程，也没有随查询扩展的带来源证据树。[DORA 论文](https://academic.oup.com/nar/article/52/W1/W54/7671306)。

### 7.2 Human AGEs

真实网址为 https://archeogenomics.eu/ ，教程为 https://archeogenomics.eu/en/map ，源码为 https://github.com/wooksh/Human_AGEs ，论文为 https://doi.org/10.1093/nar/gkad428 。此前检索容易失败，原因包括名称与 ageing genomics 混淆、站点对部分抓取器返回限制；论文正文和开源仓库一致确认该地址。

Human AGEs 是交互式时空地图与 graph database：支持用户上传 CSV/JSON，展示 Y-DNA、mtDNA、admixture、UMAP/PCA 和自定义属性；地图层可用 point、heatmap、pie chart、tag cloud，可按时间、区域和属性过滤，并导出图片或 session。论文报告其图数据库还包含人工整理的 archaeological culture regions。[Human AGEs 论文全文](https://pmc.ncbi.nlm.nih.gov/articles/PMC10320146/)。它同样属于数据探索/可视分析产品，缺少问题驱动的证据搜集、出处分级和叙事树生长机制。

**结论：可行，两个产品与网址均已核实。** 市场上已有动态古 DNA 地图和交互分析，不能把“动态地图”单独视为产品空白。  
**替代方案：** 产品差异应落在 Agent 的证据调查过程、第三人称叙事、可展开证据树、跨古基因组—考古—地名来源链接和明确的不确定性表达。

## 8. 足以影响项目成败的其他隐患

### 8.1 现场断网还会影响模型调用和地图底图

“所有数据本地化”只解决数据库访问。若 Agent 使用云端 LLM API，断网时仍会失效；地图若直接加载 OpenStreetMap/Mapbox tiles，同样会出现空白。现场版本需要本地模型或固定可重放的 Agent action fallback，并准备本地 vector tiles/PMTiles、低分辨率离线底图或自绘边界。该条件应在写代码前与赛事现场网络规则一起确认。

### 8.2 AADR 坐标精度和时间精度没有统一空间误差模型

`.anno` 的经纬度可能代表遗址、附近城镇或论文中近似点；日期可能是 direct C14 mean，也可能是 contextual range 的均值。地图不能用高倍缩放暗示米级准确度，时间轴不能只保留单点。SQLite 至少保留 `date_type`、mean、SD、full interval、location_precision`（未知也可）和原始文本。

### 8.3 同一图上混合了“观测”“论文结论”“重新计算”和“编辑连接”

证据图需要给每条边固定 provenance：`source_asserted`、`pipeline_derived`、`editorial_link`、`agent_hypothesis`。若不分层，Agent 很容易把 PCA 邻近、同一文化标签和亲缘关系写成同一种“联系”。用户可见边必须能展开到 DOI、supplement table 或构建制品版本。

### 8.4 AADR 大包下载成功不等于现场可快速查询

最新 `.geno` 为 6.7 GiB `transpose_packed`，旧工具不兼容；Poseidon PLINK mirror 约 4.6 GB，trident 解包有内存峰值。全量下载、转换、LD pruning 和 PCA 应在准备期完成。现场加载 SQLite 与小型数组，避免首次启动扫描全量 genotype。

### 8.5 论文事实可引用，论文图像与补充表的再分发许可各异

AADR 的 CC0 不会传递给 Nature、Cell 等论文版面、照片和 supplementary figures。应用可保存 DOI、table locator、结构化事实和自制图；复制论文图、墓葬照片或完整 supplement 到公开代码仓库前要逐项检查许可证。Shimao 论文页面当前标注 CC BY-NC-ND 4.0，商业展示与改编图尤其需要谨慎。[Shimao rights](https://www.nature.com/articles/s41586-025-09799-x)。

### 8.6 “任意问题”需要先做证据覆盖判断

公共数据在空间和时代上的分布很不均。Agent 收到地名后，应先查询本地库中可用样本、年代范围、可引用考古来源和缺口，再决定能否形成叙事；空间或时间范围发生扩大时，界面应明确显示。这个机制能把数据空白变成可解释的调查结果，也能避免在没有证据的地区生成连贯故事。

## 9. 推荐的离线数据组织

一周原型可使用以下最小结构：

```text
artifacts/
  catalog.sqlite        # 人、遗址、时间、来源、证据边、ID 映射、Agent 可调用查询
  numeric/
    samples.npy         # 固定顺序的样本/表示索引
    pca.npy             # 预计算坐标及 reference/projection 元信息
    f3.npy              # 预计算 point estimate、SE、有效 SNP 数
    sharing.npy         # pairwise allele-sharing / distance
    manifest.json       # AADR release、构建参数、软件版本、hash、列语义
  map/
    local.pmtiles       # 或小型离线矢量底图
  sources/
    citations.json      # DOI、URL、table locator、license、retrieved date
```

SQLite 的人级主表使用内部 UUID；AADR/Poseidon/论文 ID 进入 `external_ids` 表。遗传表示表连接 `person_uuid`，允许一个人对应多个 `Genetic ID`。所有树边进入统一 `evidence_edges` 表并带 `relation_type`、`evidence_level`、`source_id`、`source_locator`、`derived_by`、`confidence`、`review_status`。这套结构给个人 DNA 上传、HLA/SNP/CNV/表观组等后续可能模块保留扩展空间，同时无需在本周实现它们。

## 10. 汇总表

| 数据源 / 工具 | 结论 | 最大风险 | 替代方案 |
|---|---|---|---|
| AADR v66.p1 metadata | 可行 | 多数据表示、ID 层级、日期/坐标精度不统一 | 人级与表示级分表，固定 release，保留原始字段 |
| AADR v66.p1 genotype | 可行 | 6.7 GiB `tgeno`、旧工具不兼容、现场处理慢 | 构建期转换和裁剪；现场加载 PGEN/NPY 子集 |
| Poseidon `.janno` | 可行 | 标准亲缘列在 AADR 包中 0% 填充 | 解析 `AADR_Family_Relations` 与论文补充表 |
| Poseidon AADR Archive | 可行 | 社区镜像、约 4.6 GB、trident 解包内存峰值 | 用于格式获取，引用仍指向 AADR 与原论文 |
| trident | 可行 | 大包 fetch 的内存峰值 | Python 直接读 TSV/YAML；只在构建期使用 trident |
| PLINK 1.9 | 可行 | 官网 Mac 包未单列 ARM | Bioconda 原生 `osx-arm64` |
| PLINK 2.0 | 可行 | Alpha 版本持续更新 | 固定 2026-08-18 M1 build 与 checksum |
| EIGENSOFT | 可行 | 官方 9.0.0 标注 Linux only | Bioconda ARM64 8.0.0；Python/PLINK 2 做现场制品 |
| ADMIXTOOLS | 可行 | 源码编译依赖多 | Bioconda ARM64 8.0.2；预计算 f3 |
| READv2 | 部分可行 | pseudohaploid、damage、normalization 对输入敏感 | 首版用论文已报告亲缘边 |
| HaploGrep 3 | 可行 | 需要 mtDNA VCF/FASTA 与 Java 11+ | 首版使用 AADR/论文已报告 mtDNA haplogroup |
| Python PCA | 可行 | missingness projection、allele orientation、axis shrink | 与 smartpca 固定 fixture 对照后预计算 |
| Python outgroup-f3 | 部分可行 | block jackknife、遗传图谱与 pseudohaploid 方差 | 与 qp3Pop 对照；现场只读已验证结果 |
| Python allele-sharing | 可行 | pairwise 有效 SNP 集不同，易被误读为亲缘 | 同时展示共同 SNP 数和 uncertainty |
| CHGIS V6 | 部分可行 | 商业/再分发许可、地域与早期时段覆盖 | 只导入审核子集；Wikidata/论文/官方遗址源补充 |
| Wikidata | 部分可行 | SPARQL 限流；考古年代和引用质量低 | 预取 QID 子集，年代由论文覆盖 |
| 论文亲缘补充表 | 可行 | 格式不统一、关系需人工复核 | 人工策展一个 pedigree，逐边保存 table locator |
| DORA | 已核实 | 已覆盖动态地图与多种分析 | 差异化放在 Agent 调查与证据树 |
| Human AGEs | 已核实 | 已覆盖动态图层、时序过滤和 graph database | 差异化放在来源分级、叙事和可展开证据关系 |
| 云端 LLM / 在线地图 | 现场不可依赖 | 断网直接失效 | 本地模型或确定性 fallback；本地 PMTiles/矢量底图 |

最终判断：**数据与工具链整体可行，完整“全域、任意问题、现场实时科研分析”部分可行。** 一周版本应把工作量放在源数据固定、ID 映射、证据边审计、离线制品和一个可重放的 Agent 调查流程；地域与故事章节应在数据审计后选择，本报告不预设候选地区优先级。
