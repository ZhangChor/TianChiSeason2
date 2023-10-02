# 2017年天池大赛智慧航空AI大赛第二赛季赛题的一种列生成求解方法
## 1. 赛题
数据来源，赛题要求等相关信息，请参考赛题页面。  
[智慧航空AI大赛](https://tianchi.aliyun.com/competition/entrance/231609/information
)
## 2. 主要内容
整体使用列生成框架来求解航班恢复问题，使用提前或延误航班、更换飞机或飞机机型、拉直联程航班和取消航班的调整策略，对时间长度为4天，恢复期约3天的
航班进行恢复。难点在于，航班恢复问题是一个NP-Hard问题，数据量多，决策空间巨大，问题求解难度高。主要的建模思路来源于同济大学梁哲教授的这篇论文
[A column generation-based heuristic for aircraft recovery problem with airport capacity constraints and maintenance flexibility
](https://www.sciencedirect.com/science/article/pii/S0191261517310421)，但具体求解过程略有不同。
---
数据简单描述
![](/img/data_script.png)  

## 3. 项目运行需求
1. 必须安装docplex，最好是教育版。因为非教育激活版最大变量数是1000个，在解决大规模问题时，变量数远大于1000个。先安装CPLEX，并激活教育版，
再在Python环境中安装docplex，就可以在Python环境中使用没有最大变量限制的docplex了；
2. 一些常见依赖库，pandas和numpy。

## 4. 运行命令
1. 激活docplex所在虚拟环境；
2. 运行main.py；
```shell
python main.py
```
3. 运行结果保存在`/solution`文件下，其中`.csv`文件中保存了每次目标函数值下降时的解的相关信息；
`.txt`文件中保存了每次迭代的主要指标的变化。  

备注：默认采用并行计算子问题的方法，会根据运行机器的最大CPU数自动设置进程数。

