# 相似三角形练习题

## 基础练习

### 练习1：识别相似三角形
在给定的图形中，找出所有相似的三角形对，并说明理由。

**图形描述：**
- 三角形 \(ABC\) 中，点 \(D\) 在 \(AB\) 上，点 \(E\) 在 \(AC\) 上
- \(DE \parallel BC\)

**要求：**
1. 找出相似的三角形对
2. 说明每个相似关系的理由

### 练习2：书写证明格式
根据以下条件，写出相似三角形的证明过程。

**已知：**
- 在 \(\triangle ABC\) 和 \(\triangle DEF\) 中
- \(\angle A = \angle D = 90^\circ\)
- \(\angle B = \angle E\)

**要求：**
按照标准格式写出证明过程。

## 进阶练习

### 练习3：利用相似求边长
在 \(\triangle ABC\) 中，\(D\) 是 \(AB\) 上一点，\(DE \parallel BC\) 交 \(AC\) 于 \(E\)。

**已知：**
- \(AD = 2\)，\(DB = 3\)
- \(BC = 5\)

**求：**
\(DE\) 的长度。

### 练习4：综合应用
在四边形 \(ABCD\) 中，对角线 \(AC\) 和 \(BD\) 相交于点 \(O\)。

**已知：**
- \(AO = 2\)，\(OC = 3\)
- \(BO = 4\)，\(OD = 6\)

**求：**
1. 证明 \(\triangle AOB \sim \triangle COD\)
2. 求 \(\frac{AB}{CD}\) 的值

## 挑战题

### 练习5：复杂图形中的相似
在三角形 \(ABC\) 中，\(D\) 是 \(BC\) 上一点，\(AD\) 是角平分线。

**已知：**
- \(AB = 6\)，\(AC = 8\)
- \(BD = 3\)

**求：**
1. 证明 \(\triangle ABD \sim \triangle ADC\)（如果相似的话）
2. 求 \(DC\) 的长度

## 参考答案

### 练习1答案：
- \(\triangle ADE \sim \triangle ABC\)
- 理由：\(DE \parallel BC\)，所以 \(\angle ADE = \angle ABC\)（同位角），\(\angle AED = \angle ACB\)（同位角），加上公共角 \(A\)，满足AA判定法

### 练习2答案：
```
在 △ABC 和 △DEF 中，
∵ ∠A = ∠D = 90° （已知）
   ∠B = ∠E （已知）
∴ △ABC ∼ △DEF （AA判定法）
```

### 练习3答案：
因为 \(DE \parallel BC\)，所以 \(\triangle ADE \sim \triangle ABC\)

根据相似三角形性质：\(\frac{AD}{AB} = \frac{DE}{BC}\)

已知 \(AD = 2\)，\(DB = 3\)，所以 \(AB = AD + DB = 5\)

代入比例式：\(\frac{2}{5} = \frac{DE}{5}\)

解得：\(DE = 2\)

### 练习4答案：
1. 证明：
```
在 △AOB 和 △COD 中，
∵ ∠AOB = ∠COD （对顶角相等）
   \(\frac{AO}{CO} = \frac{2}{3}\)
   \(\frac{BO}{DO} = \frac{4}{6} = \frac{2}{3}\)
∴ △AOB ∼ △COD （SAS判定法）
```

2. 由相似性质：\(\frac{AB}{CD} = \frac{AO}{CO} = \frac{2}{3}\)

### 练习5答案：
1. 首先判断是否相似：
   - \(\angle ADB + \angle ADC = 180^\circ\)（平角）
   - 如果 \(\angle ADB = \angle ADC\)，则都等于 \(90^\circ\)
   - 但题目未说明 \(AD \perp BC\)，所以不能直接得出

2. 根据角平分线定理：\(\frac{AB}{AC} = \frac{BD}{DC}\)

代入已知：\(\frac{6}{8} = \frac{3}{DC}\)

解得：\(DC = 4\)

注意：本题中 \(\triangle ABD\) 和 \(\triangle ADC\) 不一定相似，除非 \(AD \perp BC\)。